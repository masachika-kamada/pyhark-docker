#!/usr/bin/env python

import sys
import threading
import time
import argparse
import tempfile

import numpy as np
import sounddevice as sd
import soundfile as sf
from numpy.lib.stride_tricks import sliding_window_view

import hark

import plotQuickWaveformKivy
import plotQuickSpecKivy
import plotQuickMusicSpecKivy
import plotQuickSourceKivy


class HARK_Localization(hark.NetworkDef):
    '''音源定位サブネットワークに相当するクラス。
    入力として8ch音響信号を受け取り、
    フーリエ変換、MUSIC法による音源定位、音源追跡を行い、
    その結果を図示する。
    '''

    def build(self,
              network: hark.Network,
              input:   hark.DataSourceMap,
              output:  hark.DataSinkMap):
        
        # 必要なノードを定義する
        node_localize_music = network.create(hark.node.LocalizeMUSIC)
        node_cm_identity_matrix = network.create(
            hark.node.CMIdentityMatrix,
            dispatch=hark.RepeatDispatcher)
        node_source_tracker = network.create(hark.node.SourceTracker)
        node_plotsource_kivy = network.create(
            plotQuickSourceKivy.plotQuickSourceKivy)

        # ノード間の接続（データの流れ）とパラメータを記述する
        (
            node_localize_music
            .add_input("INPUT", input["INPUT"])
            .add_input("NOISECM", node_cm_identity_matrix["OUTPUT"])
            .add_input("A_MATRIX", "tf.zip")
            .add_input("MUSIC_ALGORITHM", "SEVD")
            # .add_input("MUSIC_ALGORITHM", "GEVD")
            # .add_input("MUSIC_ALGORITHM", "GSVD")
            # .add_input("WINDOW_TYPE", "PAST")
            # .add_input("WINDOW_TYPE", "MIDDLE")
            .add_input("LOWER_BOUND_FREQUENCY", 400)
            .add_input("UPPER_BOUND_FREQUENCY", 3000)
            .add_input("WINDOW", 50)
            .add_input("PERIOD", 1)
            .add_input("NUM_SOURCE", 2)
            .add_input("DEBUG", False)
        )
        (
            node_cm_identity_matrix
            .add_input("NB_CHANNELS", 8)
            .add_input("LENGTH", 512)
        )
        (
            node_source_tracker
            .add_input("INPUT", node_localize_music["OUTPUT"])
            .add_input("THRESH", 34.0)
            .add_input("PAUSE_LENGTH", 1200.0)
            .add_input("MIN_SRC_INTERVAL", 20.0)
            .add_input("MIN_ID", 0)
            .add_input("DEBUG", False)
        )
        (
            node_plotsource_kivy
            .add_input("SOURCES", node_source_tracker["OUTPUT"])
        )
        (
            output
            .add_input("OUTPUT", node_source_tracker["OUTPUT"])
        )

        # ネットワークに含まれるノードの一覧をリストにする
        r = [
            node_localize_music,
            node_cm_identity_matrix,
            node_source_tracker,
            node_plotsource_kivy,
        ]

        # ノード一覧のリストを返す
        return r
    

class HARK_Main(hark.NetworkDef):
    '''メインネットワークに相当するクラス。
    入力として8ch音響信号を受け取り、
    フーリエ変換、MUSIC法による音源定位、音源追跡を行い、
    その結果を図示する。
    '''

    def build(self,
              network: hark.Network,
              input:   hark.DataSourceMap,
              output:  hark.DataSinkMap):

        # 必要なノードを定義する。
        # メインネットワークには全体の入出力を扱う
        # Publisher と Subscriber が必要。
        # さらに、AudioStreamFromMemoryノード、
        # MultiFFTノード、音源定位サブネットワークを定義する。
        node_publisher = network.create(
            hark.node.PublishData,
            dispatch=hark.RepeatDispatcher,
            name="Publisher")
        node_subscriber = network.create(
            hark.node.SubscribeData,
            name="Subscriber")

        node_audio_stream_from_memory = network.create(
            hark.node.AudioStreamFromMemory,
            dispatch=hark.TriggeredMultiShotDispatcher)
        node_multi_fft = network.create(hark.node.MultiFFT)
        node_localization = network.create(
            HARK_Localization,
            name="HARK_Localization")

        # ノード間の接続（データの流れ）を記述する
        (
            node_audio_stream_from_memory
            .add_input("INPUT", node_publisher["OUTPUT"])
            .add_input("CHANNEL_COUNT", 8)
        )
        (
            node_multi_fft
            .add_input("INPUT", node_audio_stream_from_memory["AUDIO"])
        )
        (
            node_localization
            .add_input("INPUT", node_multi_fft["OUTPUT"])
        )
        (
            node_subscriber
            .add_input("INPUT", node_localization["OUTPUT"])
        )

        # ネットワークに含まれるノードの一覧をリストにして返す
        r = [
            node_publisher,
            node_subscriber,
            node_audio_stream_from_memory,
            node_multi_fft,
            node_localization,
        ]
        return r


def main():

    def int_or_str(text):
        """Helper function for argument parsing."""
        try:
            return int(text)
        except ValueError:
            return text

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        '-l', '--list-devices', action='store_true',
        help='show list of audio devices and exit')
    args, remaining = parser.parse_known_args()
    if args.list_devices:
        print(sd.query_devices())
        parser.exit(0)
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[parser])
    parser.add_argument(
        'filename', nargs='?', metavar='FILENAME',
        help='audio file to store recording to')
    parser.add_argument(
        '-d', '--device', type=int_or_str,
        help='input device (numeric ID or substring)')
    parser.add_argument(
        '-r', '--samplerate', type=int, help='sampling rate')
    parser.add_argument(
        '-c', '--channels', type=int, default=1, help='number of input channels')
    parser.add_argument(
        '-t', '--subtype', type=str, help='sound file subtype (e.g. "PCM_24")')
    args = parser.parse_args(remaining)

    if args.samplerate is None:
        device_info = sd.query_devices(args.device, 'input')
        # soundfile expects an int, sounddevice provides a float:
        args.samplerate = int(device_info['default_samplerate'])
    if args.channels is None:
        device_info = sd.query_devices(args.device, 'input')
        args.channels = device_info['max_input_channels']
    if args.filename is None:
        args.filename = tempfile.mktemp(prefix='practice3-1a_',
                                        suffix='.wav', dir='')

    # メインネットワークを構築
    network = hark.Network.from_networkdef(HARK_Main, name="HARK_Main")

    # メインネットワークへの入出力を構築
    publisher = network.query_nodedef("Publisher")
    subscriber = network.query_nodedef("Subscriber")

    def received(data):
        print(data)
        pass

    subscriber.receive = received

    def callback(indata, frames, time, status):
        print(indata.shape, time.currentTime)
        publisher.push(indata.T)

    # ネットワーク実行用スレッドを立ち上げ
    th = threading.Thread(target=network.execute)
    th.start()

    # ネットワーク実行
    try:
        with sd.InputStream(samplerate=args.samplerate, blocksize=160,
                            device=args.device, dtype=np.int16,
                            channels=args.channels, callback=callback) as stream:
            print('#' * 75)
            print('press Ctrl+C to stop the recording')
            print('#' * 75)
            th.join()
            # while th.is_alive():
            #     time.sleep(0.1)
            
    except KeyboardInterrupt:
        print('\nRecording finished: ' + repr(args.filename))
        parser.exit(0)
    except Exception as e:
        parser.exit(type(e).__name__ + ': ' + str(e))

    # 終了処理
    finally:
        publisher.close()
        network.stop()
        th.join()


if __name__ == '__main__':
    main()

# end of file
