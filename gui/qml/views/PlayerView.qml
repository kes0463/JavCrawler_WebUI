import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import ".."
import "../components"

Item {
    id: playerRoot

    property string productCode: ""
    property url videoSource: ""
    property string title: ""

    // 시각적 상태
    property bool showControls: true
    property bool isPip: false

    // 애니메이션 제어용
    property rect startRect: Qt.rect(0, 0, 0, 0)

    // 스킵 감지용 이전 위치 추적
    property int _prevPosition: 0
    property bool _isUserSeeking: false

    // --- 비디오 엔진 ---
    MediaPlayer {
        id: mediaPlayer
        source: playerRoot.videoSource
        videoOutput: videoOutput
        audioOutput: AudioOutput { id: audioOutput; volume: volumeSlider.value }

        onPlaybackStateChanged: {
            if (playbackState === MediaPlayer.PlayingState) {
                PlayerModel.startWatch(playerRoot.productCode, duration / 1000)
            }
        }

        onPositionChanged: {
            var pos = position

            // 스킵 감지: 이전 위치보다 5초 이상 앞으로 점프 → 사용자 스킵
            if (!playerRoot._isUserSeeking && playerRoot._prevPosition > 0) {
                var jump = pos - playerRoot._prevPosition
                if (jump > 5000 && jump < 3600000) {
                    PlayerModel.recordSkip(playerRoot.productCode, playerRoot._prevPosition, pos)
                }
            }
            playerRoot._prevPosition = pos

            // 약 5초마다 DB에 진척도 저장
            if (pos > 0 && pos % 5000 < 500) {
                PlayerModel.updateProgress(playerRoot.productCode, pos, duration / 1000)
            }
        }
    }

    // 30초마다 누적 시청 시간 저장
    Timer {
        id: durationTimer
        interval: 30000
        repeat: true
        running: mediaPlayer.playbackState === MediaPlayer.PlayingState
        onTriggered: {
            PlayerModel.updateWatchDuration(playerRoot.productCode, 30)
        }
    }

    Rectangle {
        id: bgRect
        anchors.fill: parent
        color: "#000000"
        opacity: 0

        states: [
            State {
                name: "visible"
                PropertyChanges { target: bgRect; opacity: 1.0 }
            }
        ]
        transitions: Transition {
            NumberAnimation { property: "opacity"; duration: 400 }
        }
    }

    // 비디오 출력 영역 (애니메이션 대상)
    Rectangle {
        id: videoContainer
        x: playerRoot.startRect.x
        y: playerRoot.startRect.y
        width: playerRoot.startRect.width
        height: playerRoot.startRect.height
        color: "transparent"
        clip: true

        VideoOutput {
            id: videoOutput
            anchors.fill: parent
            fillMode: VideoOutput.PreserveAspectFit

            TapHandler {
                onTapped: {
                    if (mediaPlayer.playbackState === MediaPlayer.PlayingState) mediaPlayer.pause()
                    else mediaPlayer.play()
                    playerRoot.showControls = true
                }
            }
        }

        states: [
            State {
                name: "fullscreen"
                PropertyChanges {
                    target: videoContainer;
                    x: 0; y: 0;
                    width: playerRoot.width;
                    height: playerRoot.height
                }
            }
        ]

        transitions: Transition {
            NumberAnimation {
                properties: "x,y,width,height";
                duration: 500;
                easing.type: Easing.OutExpo
            }
        }
    }

    // 컨트롤 숨김 타이머 (4초 후 자동 숨김)
    Timer {
        id: controlHideTimer
        interval: 4000
        repeat: false
        running: mediaPlayer.playbackState === MediaPlayer.PlayingState && playerRoot.showControls
        onTriggered: playerRoot.showControls = false
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        propagateComposedEvents: true
        onPositionChanged: {
            playerRoot.showControls = true
            controlHideTimer.restart()
        }
        onClicked: (mouse) => mouse.accepted = false
    }

    // --- 하단 컨트롤 바 (Glassmorphism) ---
    Rectangle {
        id: controlBar
        anchors.bottom: parent.bottom
        width: parent.width
        height: 140
        visible: playerRoot.showControls || mediaPlayer.playbackState !== MediaPlayer.PlayingState
        opacity: visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 300 } }

        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.92) }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            anchors.bottomMargin: 16
            spacing: 8

            // 재생바
            Slider {
                id: progressSlider
                Layout.fillWidth: true
                from: 0
                to: Math.max(1, mediaPlayer.duration)
                value: mediaPlayer.position
                onPressedChanged: {
                    playerRoot._isUserSeeking = pressed
                }
                onMoved: mediaPlayer.setPosition(value)

                background: Rectangle {
                    height: 6; radius: 3; color: Qt.rgba(255, 255, 255, 0.12)
                    Rectangle {
                        width: progressSlider.visualPosition * parent.width
                        height: parent.height; radius: 3; color: Theme.accentNeon
                    }
                }
                handle: Rectangle {
                    x: progressSlider.visualPosition * (progressSlider.width - width)
                    y: (progressSlider.height - height) / 2
                    width: 14; height: 14; radius: 7; color: "#FFFFFF"
                    border.color: Theme.accentNeon; border.width: 2
                    visible: progressSlider.hovered || progressSlider.pressed
                    scale: progressSlider.hovered ? 1.2 : 1.0
                    Behavior on scale { NumberAnimation { duration: 100 } }
                }
            }

            RowLayout {
                spacing: 16

                // 재생/일시정지
                Button {
                    id: playPauseBtn
                    flat: true
                    font.pixelSize: 26
                    onClicked: mediaPlayer.playbackState === MediaPlayer.PlayingState
                        ? mediaPlayer.pause() : mediaPlayer.play()
                    contentItem: Text {
                        text: mediaPlayer.playbackState === MediaPlayer.PlayingState ? "⏸" : "▶"
                        color: "#FFFFFF"; font: parent.font
                        horizontalAlignment: Text.AlignHCenter
                    }
                    background: Rectangle { color: "transparent" }
                    scale: playPauseBtn.hovered ? 1.15 : 1.0
                    Behavior on scale { NumberAnimation { duration: 100 } }
                }

                // 시간 표시
                Text {
                    text: formatTime(mediaPlayer.position) + " / " + formatTime(mediaPlayer.duration)
                    color: Qt.rgba(255, 255, 255, 0.75)
                    font.pixelSize: 14
                    font.family: Theme.fontFamily
                }

                // 10초 뒤로
                Button {
                    flat: true; font.pixelSize: 18
                    contentItem: Text { text: "⏪"; color: "#FFFFFF"; font: parent.font }
                    background: Rectangle { color: "transparent" }
                    onClicked: mediaPlayer.setPosition(Math.max(0, mediaPlayer.position - 10000))
                    ToolTip { text: "10초 뒤로"; visible: parent.hovered; delay: 500 }
                }

                // 10초 앞으로
                Button {
                    flat: true; font.pixelSize: 18
                    contentItem: Text { text: "⏩"; color: "#FFFFFF"; font: parent.font }
                    background: Rectangle { color: "transparent" }
                    onClicked: mediaPlayer.setPosition(
                        Math.min(mediaPlayer.duration, mediaPlayer.position + 10000)
                    )
                    ToolTip { text: "10초 앞으로"; visible: parent.hovered; delay: 500 }
                }

                Item { Layout.fillWidth: true }

                // ── 피드백 영역 ──────────────────────────────

                // 별점 위젯
                RatingWidget {
                    id: ratingWidget
                    rating: PlayerModel.currentRating
                    starSize: 20
                    Layout.alignment: Qt.AlignVCenter
                    onRatingSelected: function(r) {
                        PlayerModel.setRating(playerRoot.productCode, r)
                        window.showToast(r > 0 ? "별점 " + r + "점 저장!" : "별점 초기화", "success")
                    }
                }

                // 좋아요 버튼
                Button {
                    id: likeBtn
                    flat: true; font.pixelSize: 20
                    property bool active: PlayerModel.isLiked
                    contentItem: Text {
                        text: "❤"
                        color: likeBtn.active ? "#FF4081" : Qt.rgba(255, 255, 255, 0.5)
                        font: parent.font
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }
                    background: Rectangle {
                        color: "transparent"
                        radius: 8
                        border.color: likeBtn.active ? Qt.rgba(255, 64, 129, 0.4) : "transparent"
                        border.width: 1
                    }
                    scale: likeBtn.hovered ? 1.2 : (likeBtn.active ? 1.1 : 1.0)
                    Behavior on scale { NumberAnimation { duration: 120 } }
                    onClicked: {
                        PlayerModel.setLike(playerRoot.productCode)
                        if (PlayerModel.isLiked)
                            window.showToast("좋아요! 취향에 반영됩니다 ❤", "success")
                        else
                            window.showToast("좋아요를 취소했습니다", "info")
                    }
                    ToolTip { text: "좋아요 (+취향점수)"; visible: parent.hovered; delay: 500 }
                }

                // 싫어요 버튼
                Button {
                    id: dislikeBtn
                    flat: true; font.pixelSize: 20
                    property bool active: PlayerModel.isDisliked
                    contentItem: Text {
                        text: "👎"
                        color: dislikeBtn.active ? "#FF6B6B" : Qt.rgba(255, 255, 255, 0.5)
                        font: parent.font
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }
                    background: Rectangle {
                        color: "transparent"
                        radius: 8
                        border.color: dislikeBtn.active ? Qt.rgba(255, 107, 107, 0.4) : "transparent"
                        border.width: 1
                    }
                    scale: dislikeBtn.hovered ? 1.2 : (dislikeBtn.active ? 1.1 : 1.0)
                    Behavior on scale { NumberAnimation { duration: 120 } }
                    onClicked: {
                        PlayerModel.setDislike(playerRoot.productCode)
                        if (PlayerModel.isDisliked)
                            window.showToast("취향에서 제외됩니다", "warning")
                        else
                            window.showToast("싫어요를 취소했습니다", "info")
                    }
                    ToolTip { text: "싫어요 (-취향점수)"; visible: parent.hovered; delay: 500 }
                }

                // 볼륨
                RowLayout {
                    spacing: 8
                    Text { text: "🔊"; color: "#FFFFFF"; font.pixelSize: 16 }
                    Slider {
                        id: volumeSlider
                        width: 90; from: 0; to: 1.0; value: 0.8
                        background: Rectangle {
                            height: 4; radius: 2; color: Qt.rgba(255, 255, 255, 0.15)
                            Rectangle {
                                width: volumeSlider.visualPosition * parent.width
                                height: parent.height; radius: 2; color: Theme.accentNeon
                            }
                        }
                        handle: Rectangle {
                            x: volumeSlider.visualPosition * (volumeSlider.width - width)
                            y: (volumeSlider.height - height) / 2
                            width: 12; height: 12; radius: 6; color: "#FFFFFF"
                            border.color: Theme.accentNeon; border.width: 1
                        }
                    }
                }

                // 닫기
                Button {
                    text: "✕"
                    flat: true; font.pixelSize: 18
                    contentItem: Text {
                        text: "✕"; color: Qt.rgba(255, 255, 255, 0.7)
                        font: parent.font; horizontalAlignment: Text.AlignHCenter
                    }
                    background: Rectangle {
                        color: parent.hovered ? Qt.rgba(255, 0, 0, 0.2) : "transparent"
                        radius: 6
                        Behavior on color { ColorAnimation { duration: 150 } }
                    }
                    onClicked: {
                        mediaPlayer.stop()
                        playerRoot.closeRequest()
                    }
                    ToolTip { text: "닫기"; visible: parent.hovered; delay: 500 }
                }
            }
        }
    }

    signal closeRequest()

    function formatTime(ms) {
        if (ms <= 0) return "0:00"
        var totalSec = Math.floor(ms / 1000)
        var min = Math.floor(totalSec / 60)
        var sec = totalSec % 60
        return min + ":" + (sec < 10 ? "0" + sec : sec)
    }

    // 시작 시 애니메이션 트리거
    Component.onCompleted: {
        bgRect.state = "visible"
        videoContainer.state = "fullscreen"
        mediaPlayer.play()
        // 별점·좋아요 상태 초기화
        ratingWidget.rating = PlayerModel.getRatingForProduct(playerRoot.productCode)
    }

    // PlayerModel 신호 연결
    Connections {
        target: PlayerModel
        function onRatingChanged(r) { ratingWidget.rating = r }
    }
}