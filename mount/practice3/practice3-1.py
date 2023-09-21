#!/usr/bin/env python

'''PyHARK（オンライン処理）で音源定位を行うプログラム。
引数としてTAMAGOで収録した8ch音響信号を受け取り、
逐次的に音源定位を行い結果を表示する。
'''

import sys
import threading
import time

import numpy as np
import soundfile as sf
from numpy.lib.stride_tricks import sliding_window_view

import hark

# import plotQuickWaveformKivy
# import plotQuickSpecKivy
# import plotQuickMusicSpecKivy
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
            .add_input("LOWER_BOUND_FREQUENCY", 3000)
            .add_input("UPPER_BOUND_FREQUENCY", 6000)
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
            .add_input("THRESH", 28.0)
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
            .add_input("OUTPUT", node_plotsource_kivy["OUTPUT"])
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
    '''メインネットワークを構築・実行し、
    コマンドライン引数で指定されたWAVファイルを読み込んで
    メインネットワークに逐次的に publish する。
    '''
    
    # コマンドライン引数の処理
    if len(sys.argv) < 2:
        print("no input file")
        return
    wavfilename = sys.argv[1]


    # メインネットワークを構築
    network = hark.Network.from_networkdef(HARK_Main, name="HARK_Main")

    # メインネットワークへの入出力を構築
    publisher = network.query_nodedef("Publisher")
    subscriber = network.query_nodedef("Subscriber")

    # subscriber がデータを受け取ったとき
    # （メインネットワークが結果を出力したとき）に
    # 実行される動作を定義する。
    # ここでは pass を用いることで「何もしない」ことを指示する。
    def received(data):
        pass

    subscriber.receive = received

    # 入力ファイル読み込み・フレーム分割
    audio, rate = sf.read(wavfilename, dtype=np.int16)
    advance = 160
    frames = sliding_window_view(audio, advance, axis=0)[::advance, :, :]

    # ネットワーク実行用スレッドを立ち上げ
    th = threading.Thread(target=network.execute)
    th.start()

    # ネットワーク実行
    try:
        # フレームごとに処理
        for t, f in enumerate(frames):
            # もしネットワーク実行用スレッドが停止していたら
            # ループを抜け処理全体を停止させる
            if not th.is_alive():
                break

            # ネットワークに1フレーム分の音響信号を送信
            publisher.push(f)

            # リアルタイム処理と同等程度の処理時間となるように
            # 音響信号送信間隔を調整する
            time.sleep(advance / rate)

    # 終了処理
    finally:
        publisher.close()
        network.stop()
        th.join()


if __name__ == '__main__':
    main()

# end of file
