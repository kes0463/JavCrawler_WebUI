import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import QtCore
import ".."
import "../components"

Item {
    id: playerRoot
    focus: true

    property string productCode: ""
    property url videoSource: ""
    property string title: ""
    property int resumePosition: 0        // ms 단위, 0 = 처음부터

    /** 멀티 파트 연속 재생: 로컬 파일 경로 문자열 목록 (QML 배열) */
    property var videoPlaylist: []
    property int playlistIndex: 0
    /** DB·자막용 현재 파일 로컬 경로 */
    property string currentVideoFilePath: ""

    property bool showControls: true
    property bool isPip: false
    property rect startRect: Qt.rect(0, 0, 0, 0)

    // 이어보기 seek 완료 여부 (중복 seek 방지)
    property bool _seekDone: false
    // 소스 주입 직후 자동 재생 보장용(Loaded 이전 play() 유실 방지)
    property bool _autoPlayPending: false

    // 스킵 감지용
    property int _prevPosition: 0
    property bool _isUserSeeking: false

    // 자막
    property var subtitleTracks: []       // [{path, label, filename}]
    property int activeSubtitleIdx: -1   // -1 = 없음
    property var subtitleCues: []        // [{start_ms, end_ms, text, ass?}]
    property string currentSubtitle: ""  // SRT/SMI/VTT 폴백용 평문
    property var activeAssCues: []       // 현재 시점에 활성화된 ASS 큐 리스트

    // 전체화면 여부 (ApplicationWindow 기준)
    readonly property bool isFullscreen: window.visibility === Window.FullScreen

    // 하단 컨트롤 바: 아이콘·별·볼륨 축 통일
    readonly property int playerBarIconPx: 28
    readonly property int playerBarPlayPx: 36
    readonly property int playerSeekIconPx: 30
    readonly property int playerStarSize: 26
    readonly property int playerVolSliderW: 108
    readonly property int playerVolIconBox: 34

    // ── 볼륨 영구 저장 ──────────────────────────────────────
    Settings {
        id: playerSettings
        category: "Player"
        property real volume: 0.8
    }

    // ── 자막 설정 영구 저장 ─────────────────────────────────
    Settings {
        id: subtitleSettings
        category: "Subtitle"
        property real plainFontSize: 20        // 평문 자막 px
        property real assFontScale: 1.0        // ASS 자막 크기 배율
        property string fontFamily: ""         // "" = 테마 기본
        property string textColor: "#FFFFFF"   // 평문 자막 텍스트 색
        property real bgOpacity: 0.72          // 배경 불투명도
    }

    // ── 키보드 단축키 ────────────────────────────────────────
    // ShortcutOverride를 수락해 ApplicationShortcut이 ESC/Backspace를 먼저 소비하는 것을 막는다.
    // Qt 이벤트 흐름: ShortcutOverride 수락 → Shortcut 검사 건너뜀 → Keys.onPressed 도달
    Keys.onShortcutOverride: function(event) {
        switch (event.key) {
        case Qt.Key_Space:
        case Qt.Key_Escape:
        case Qt.Key_Backspace:
        case Qt.Key_Left:
        case Qt.Key_Right:
        case Qt.Key_Up:
        case Qt.Key_Down:
        case Qt.Key_Return:
        case Qt.Key_F:
        case Qt.Key_P:
        case Qt.Key_M:
        case Qt.Key_Home:
        case Qt.Key_1: case Qt.Key_2: case Qt.Key_3: case Qt.Key_4: case Qt.Key_5:
        case Qt.Key_6: case Qt.Key_7: case Qt.Key_8: case Qt.Key_9:
            event.accepted = true
            break
        default:
            event.accepted = false
        }
    }

    Keys.onPressed: function(event) {
        switch (event.key) {
        case Qt.Key_Space:
            if (mediaPlayer.playbackState === MediaPlayer.PlayingState) {
                mediaPlayer.pause(); showOsd("⏸  일시정지")
            } else {
                mediaPlayer.play(); showOsd("▶  재생")
            }
            playerRoot.showControls = true
            event.accepted = true; break
        case Qt.Key_Escape:
        case Qt.Key_Backspace:
            if (playerRoot.isFullscreen)
                playerRoot._toggleFullscreen()
            else
                playerRoot._closePlayer()
            event.accepted = true; break
        case Qt.Key_Return:
        case Qt.Key_F:
            playerRoot._toggleFullscreen(); event.accepted = true; break
        case Qt.Key_P:
            playerRoot.isPip = !playerRoot.isPip; event.accepted = true; break
        case Qt.Key_Left:
            if (event.modifiers & Qt.ShiftModifier) {
                mediaPlayer.setPosition(Math.max(0, mediaPlayer.position - 30000))
                showOsd("◀◀  -30초")
            } else if (event.modifiers & Qt.ControlModifier) {
                mediaPlayer.setPosition(Math.max(0, mediaPlayer.position - 60000))
                showOsd("◀◀◀  -1분")
            } else {
                mediaPlayer.setPosition(Math.max(0, mediaPlayer.position - 5000))
                showOsd("◀  -5초")
            }
            event.accepted = true; break
        case Qt.Key_Right:
            if (event.modifiers & Qt.ShiftModifier) {
                mediaPlayer.setPosition(Math.min(mediaPlayer.duration, mediaPlayer.position + 30000))
                showOsd("+30초  ▶▶")
            } else if (event.modifiers & Qt.ControlModifier) {
                mediaPlayer.setPosition(Math.min(mediaPlayer.duration, mediaPlayer.position + 60000))
                showOsd("+1분  ▶▶▶")
            } else {
                mediaPlayer.setPosition(Math.min(mediaPlayer.duration, mediaPlayer.position + 5000))
                showOsd("+5초  ▶")
            }
            event.accepted = true; break
        case Qt.Key_Up:
            volumeSlider.value = Math.min(1.0, volumeSlider.value + 0.05)
            showOsd("🔊  " + Math.round(volumeSlider.value * 100) + "%")
            event.accepted = true; break
        case Qt.Key_Down:
            volumeSlider.value = Math.max(0.0, volumeSlider.value - 0.05)
            showOsd("🔊  " + Math.round(volumeSlider.value * 100) + "%")
            event.accepted = true; break
        case Qt.Key_M:
            audioOutput.muted = !audioOutput.muted
            showOsd(audioOutput.muted ? "🔇  음소거" : "🔊  음소거 해제")
            event.accepted = true; break
        case Qt.Key_Home:
            mediaPlayer.setPosition(0); showOsd("⏮  처음으로"); event.accepted = true; break
        case Qt.Key_1: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.1)); showOsd("▶  10%"); event.accepted = true; break
        case Qt.Key_2: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.2)); showOsd("▶  20%"); event.accepted = true; break
        case Qt.Key_3: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.3)); showOsd("▶  30%"); event.accepted = true; break
        case Qt.Key_4: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.4)); showOsd("▶  40%"); event.accepted = true; break
        case Qt.Key_5: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.5)); showOsd("▶  50%"); event.accepted = true; break
        case Qt.Key_6: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.6)); showOsd("▶  60%"); event.accepted = true; break
        case Qt.Key_7: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.7)); showOsd("▶  70%"); event.accepted = true; break
        case Qt.Key_8: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.8)); showOsd("▶  80%"); event.accepted = true; break
        case Qt.Key_9: mediaPlayer.setPosition(Math.floor(mediaPlayer.duration * 0.9)); showOsd("▶  90%"); event.accepted = true; break
        default: event.accepted = false
        }
    }

    // 포커스를 빼앗겼을 때 즉시 재취득 (MediaPlayer 등 내부 아이템이 포커스를 가져갈 경우 대비)
    onActiveFocusChanged: {
        if (!activeFocus && visible)
            Qt.callLater(forceActiveFocus)
    }

    function _closePlayer() {
        if (playerRoot.isFullscreen) window.visibility = Window.Windowed
        mediaPlayer.stop()
        playerRoot.closeRequest()
    }

    function _toggleFullscreen() {
        if (playerRoot.isFullscreen)
            window.visibility = Window.Windowed
        else
            window.visibility = Window.FullScreen
    }

    function showOsd(text) {
        osdText.text = text
        osdAnim.restart()
    }

    function _tryResumeSeek(trigger) {
        if (!mediaPlayer.seekable || playerRoot.resumePosition <= 5000 || playerRoot._seekDone)
            return
        var status = mediaPlayer.mediaStatus
        var ready = status === MediaPlayer.LoadedMedia
            || status === MediaPlayer.BufferedMedia
            || status === MediaPlayer.BufferingMedia
        if (!ready || mediaPlayer.duration <= 0)
            return
        playerRoot._seekDone = true
        mediaPlayer.setPosition(playerRoot.resumePosition)
    }

    // ── 자막 헬퍼 ────────────────────────────────────────────
    function loadSubtitle(idx) {
        playerRoot.activeSubtitleIdx = idx
        playerRoot.currentSubtitle = ""
        if (idx < 0 || idx >= playerRoot.subtitleTracks.length) {
            playerRoot.subtitleCues = []
            return
        }
        var path = playerRoot.subtitleTracks[idx].path
        var json = PlayerModel.loadSubtitleFile(path)
        try {
            playerRoot.subtitleCues = JSON.parse(json)
        } catch(e) {
            playerRoot.subtitleCues = []
        }
    }

    function _updateSubtitle() {
        if (playerRoot.activeSubtitleIdx < 0 || playerRoot.subtitleCues.length === 0) {
            if (playerRoot.currentSubtitle !== "")
                playerRoot.currentSubtitle = ""
            if (playerRoot.activeAssCues.length !== 0)
                playerRoot.activeAssCues = []
            return
        }
        var pos = mediaPlayer.position
        var cues = playerRoot.subtitleCues
        var foundPlain = ""
        var ass = []
        for (var i = 0; i < cues.length; i++) {
            var c = cues[i]
            if (pos < c.start_ms || pos > c.end_ms)
                continue
            if (c.ass) {
                ass.push(c)
            } else if (foundPlain === "") {
                foundPlain = c.text
            }
        }
        if (playerRoot.currentSubtitle !== foundPlain)
            playerRoot.currentSubtitle = foundPlain
        playerRoot.activeAssCues = ass
    }

    Timer {
        id: subtitleTimer
        interval: 80
        repeat: true
        running: playerRoot.activeSubtitleIdx >= 0
            && playerRoot.subtitleCues.length > 0
            && mediaPlayer.playbackState !== MediaPlayer.StoppedState
        onTriggered: playerRoot._updateSubtitle()
    }

    // ── 미디어 엔진 ──────────────────────────────────────────
    MediaPlayer {
        id: mediaPlayer
        source: playerRoot.videoSource
        videoOutput: videoOutput
        audioOutput: AudioOutput { id: audioOutput; volume: volumeSlider.value }

        onPlaybackStateChanged: {
            if (mediaPlayer.playbackState === MediaPlayer.PlayingState)
                playerRoot._autoPlayPending = false
        }

        onMediaStatusChanged: {
            // Loaded/Buffered 시점에 autoplay 요청을 확실히 소진
            if (playerRoot._autoPlayPending
                    && (mediaPlayer.mediaStatus === MediaPlayer.LoadedMedia
                        || mediaPlayer.mediaStatus === MediaPlayer.BufferedMedia)) {
                mediaPlayer.play()
            }
            playerRoot._tryResumeSeek("mediaStatusChanged")
            if (mediaPlayer.mediaStatus === MediaPlayer.EndOfMedia) {
                // 마지막 프레임에서 멈춤 — 컨트롤 표시 유지
                playerRoot.showControls = true
                PlayerModel.updateProgress(
                    playerRoot.productCode,
                    mediaPlayer.duration,
                    Math.floor(mediaPlayer.duration / 1000),
                    playerRoot.currentVideoFilePath
                )
                if (playerRoot.videoPlaylist
                        && playerRoot.videoPlaylist.length > playerRoot.playlistIndex + 1) {
                    playerRoot.playlistIndex = playerRoot.playlistIndex + 1
                    var nextPath = playerRoot.videoPlaylist[playerRoot.playlistIndex]
                    playerRoot.currentVideoFilePath = nextPath
                    playerRoot.resumePosition = PlayerModel.getLastPosition(
                        playerRoot.productCode, nextPath)
                    playerRoot._seekDone = false
                    playerRoot._prevPosition = 0
                    playerRoot._autoPlayPending = true
                    playerRoot.videoSource = Theme.pathToUrl(PlayerModel.playbackSourceFor(nextPath))
                    showOsd("▶ 다음 파트 (" + (playerRoot.playlistIndex + 1) + "/"
                        + playerRoot.videoPlaylist.length + ")")
                }
            }
        }

        // duration 확정 시 총 길이 기록
        onDurationChanged: {
            if (mediaPlayer.duration > 0)
                PlayerModel.updateTotalDuration(playerRoot.productCode, Math.floor(mediaPlayer.duration / 1000))
        }

        // seekable 상태가 되면 이어보기 seek 실행 (1회)
        onSeekableChanged: {
            playerRoot._tryResumeSeek("seekableChanged")
        }

        onPositionChanged: {
            var pos = mediaPlayer.position
            if (playerRoot.activeSubtitleIdx >= 0)
                playerRoot._updateSubtitle()
            // 스킵 감지 (5초 이상 앞으로 점프)
            if (!playerRoot._isUserSeeking && playerRoot._prevPosition > 0) {
                var jump = pos - playerRoot._prevPosition
                if (jump > 5000 && jump < 3600000)
                    PlayerModel.recordSkip(playerRoot.productCode, playerRoot._prevPosition, pos)
            }
            playerRoot._prevPosition = pos
        }

    }

    // 소스가 늦게 주입되는 구조(Loader + Qt.callLater)라서,
    // videoSource가 설정되는 순간 재생을 시작한다.
    onVideoSourceChanged: {
        playerRoot._seekDone = false
        playerRoot._prevPosition = 0
        playerRoot._autoPlayPending = true
        playerRoot.reloadSubtitleTracks()
        if (playerRoot.videoSource && playerRoot.videoSource.toString() !== "") {
            if (mediaPlayer.playbackState !== MediaPlayer.PlayingState) {
                mediaPlayer.play()
            }
        }
    }

    // 재생 위치 5초마다 저장
    Timer {
        id: progressTimer
        interval: 5000; repeat: true
        running: mediaPlayer.playbackState === MediaPlayer.PlayingState
        onTriggered: {
            if (mediaPlayer.position > 0)
                PlayerModel.updateProgress(
                    playerRoot.productCode,
                    mediaPlayer.position,
                    Math.floor(mediaPlayer.duration / 1000),
                    playerRoot.currentVideoFilePath
                )
        }
    }

    // 누적 시청 시간 30초마다 저장
    Timer {
        id: durationTimer
        interval: 30000; repeat: true
        running: mediaPlayer.playbackState === MediaPlayer.PlayingState
        onTriggered: PlayerModel.updateWatchDuration(playerRoot.productCode, 30)
    }

    // ── 검은 배경 오버레이 ───────────────────────────────────
    Rectangle {
        id: bgRect
        anchors.fill: parent
        color: "#000000"
        opacity: 0
        visible: !playerRoot.isPip
        states: State {
            name: "visible"
            PropertyChanges { target: bgRect; opacity: 1.0 }
        }
        transitions: Transition {
            NumberAnimation { property: "opacity"; duration: 350 }
        }
    }

    // ── PIP 상태: 우하단 작은 창 ─────────────────────────────
    // 단일 상태 기계로 통합 — videoContainer.states 제거, 여기서만 관리
    onIsPipChanged: playerRoot.state = playerRoot.isPip ? "pip" : "normal"

    states: [
        State {
            name: "normal"
            PropertyChanges { target: videoContainer; x: 0; y: 0; width: playerRoot.width; height: playerRoot.height; radius: 0 }
        },
        State {
            name: "pip"
            PropertyChanges { target: videoContainer; x: playerRoot.width - 404; y: playerRoot.height - 232; width: 400; height: 225; radius: 10 }
        }
    ]
    transitions: Transition {
        NumberAnimation { properties: "x,y,width,height,radius"; duration: 300; easing.type: Easing.OutCubic }
    }

    // ── 비디오 컨테이너 ─────────────────────────────────────
    Rectangle {
        id: videoContainer
        x: playerRoot.startRect.x
        y: playerRoot.startRect.y
        width: playerRoot.startRect.width
        height: playerRoot.startRect.height
        color: "#000"
        clip: true

        VideoOutput {
            id: videoOutput
            anchors.fill: parent
            fillMode: VideoOutput.PreserveAspectFit
        }

        // 영상 화면 클릭: 재생/일시정지 (PIP이면 PIP 해제)
        // TapHandler가 환경에 따라 누락되는 케이스가 있어 MouseArea로 보강
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton
            onDoubleClicked: playerRoot._toggleFullscreen()
            onClicked: {
                if (playerRoot.isPip) {
                    playerRoot.isPip = false
                    return
                }
                mediaPlayer.playbackState === MediaPlayer.PlayingState
                    ? mediaPlayer.pause()
                    : mediaPlayer.play()
                playerRoot.showControls = true
                controlHideTimer.restart()
            }
        }

        // PIP 닫기 버튼
        Rectangle {
            visible: playerRoot.isPip
            anchors.top: parent.top; anchors.right: parent.right
            anchors.margins: 6
            width: 24; height: 24; radius: 12
            color: pipCloseMa.containsMouse ? "#CC0000" : "#88000000"
            Text { anchors.centerIn: parent; text: "✕"; color: "#FFF"; font.pixelSize: 12 }
            MouseArea {
                id: pipCloseMa
                anchors.fill: parent
                hoverEnabled: true
                onClicked: playerRoot._closePlayer()
            }
        }

    }

    // ── 자막 오버레이 ────────────────────────────────────────
    // SRT/SMI/VTT 평문 폴백 (ASS 큐가 활성화되면 숨김)
    Rectangle {
        id: subtitleOverlay
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: controlBar.visible && controlBar.opacity > 0.1 ? controlBar.top : parent.bottom
        anchors.bottomMargin: controlBar.visible && controlBar.opacity > 0.1 ? 8 : 60
        visible: playerRoot.currentSubtitle !== ""
            && playerRoot.activeAssCues.length === 0
            && !playerRoot.isPip
        color: Qt.rgba(0, 0, 0, subtitleSettings.bgOpacity)
        radius: 6
        width: subtitleText.width + 24
        height: subtitleText.height + 12

        Text {
            id: subtitleText
            anchors.centerIn: parent
            text: playerRoot.currentSubtitle
            color: subtitleSettings.textColor
            font.pixelSize: subtitleSettings.plainFontSize
            font.family: subtitleSettings.fontFamily !== "" ? subtitleSettings.fontFamily : Theme.fontFamily
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            width: Math.min(implicitWidth, playerRoot.width * 0.85)
            textFormat: Text.PlainText
            style: Text.Outline
            styleColor: "#000000"
        }
    }

    // ASS 자막 풀 렌더 오버레이 (글꼴/색/위치/드로잉 지원)
    AssOverlay {
        id: assOverlay
        // VideoOutput의 contentRect 좌표는 VideoOutput 내부 좌표계 → 영상 영역의 부모 좌표로 변환
        videoRect: Qt.rect(
            videoContainer.x + videoOutput.x + videoOutput.contentRect.x,
            videoContainer.y + videoOutput.y + videoOutput.contentRect.y,
            videoOutput.contentRect.width,
            videoOutput.contentRect.height,
        )
        cues: playerRoot.activeAssCues
        currentPositionMs: mediaPlayer.position
        fontSizeScale: subtitleSettings.assFontScale
        anchors.fill: parent
        visible: !playerRoot.isPip
        z: subtitleOverlay.z + 1
    }

    // ── 자막 글꼴·크기 설정 팝업 ─────────────────────────────
    Popup {
        id: subtitleSettingsPopup
        width: 290
        height: subSettingsCol.implicitHeight + 28
        padding: 0
        parent: playerRoot
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Qt.rgba(0.09, 0.09, 0.11, 0.96)
            radius: 9
            border.color: Qt.rgba(1, 1, 1, 0.13)
            border.width: 1
        }

        Column {
            id: subSettingsCol
            anchors { left: parent.left; right: parent.right; top: parent.top }
            anchors.margins: 14
            anchors.topMargin: 14
            spacing: 14

            Text {
                text: "자막 설정"
                color: Qt.rgba(1, 1, 1, 0.9)
                font.pixelSize: 13; font.bold: true
                font.family: Theme.fontFamily
            }

            // ── 평문 자막 크기 ────────────────────────────────
            Column {
                width: parent.width
                spacing: 4
                Row {
                    width: parent.width
                    spacing: 0
                    Text {
                        text: "크기 (SRT·SMI·VTT)"
                        color: Qt.rgba(1, 1, 1, 0.6)
                        font.pixelSize: 11; font.family: Theme.fontFamily
                        width: 140
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: Math.round(subtitleSettings.plainFontSize) + " px"
                        color: Theme.accentNeon
                        font.pixelSize: 11; font.family: Theme.fontFamily
                        width: parent.width - 140
                        horizontalAlignment: Text.AlignRight
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Slider {
                    id: plainSizeSlider
                    width: parent.width
                    from: 12; to: 56; stepSize: 1
                    value: subtitleSettings.plainFontSize
                    focusPolicy: Qt.NoFocus
                    onMoved: subtitleSettings.plainFontSize = value
                    background: Rectangle {
                        height: 4; radius: 2; color: Qt.rgba(1, 1, 1, 0.12)
                        Rectangle {
                            width: plainSizeSlider.visualPosition * parent.width
                            height: parent.height; radius: 2; color: Theme.accentNeon
                        }
                    }
                    handle: Rectangle {
                        x: plainSizeSlider.visualPosition * (plainSizeSlider.width - width)
                        y: (plainSizeSlider.height - height) / 2
                        width: 13; height: 13; radius: 7; color: "#FFF"
                        border.color: Theme.accentNeon; border.width: 2
                    }
                }
            }

            // ── ASS 자막 크기 배율 ────────────────────────────
            Column {
                width: parent.width
                spacing: 4
                Row {
                    width: parent.width
                    spacing: 0
                    Text {
                        text: "배율 (ASS·SSA)"
                        color: Qt.rgba(1, 1, 1, 0.6)
                        font.pixelSize: 11; font.family: Theme.fontFamily
                        width: 140
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: subtitleSettings.assFontScale.toFixed(1) + "×"
                        color: Theme.accentNeon
                        font.pixelSize: 11; font.family: Theme.fontFamily
                        width: parent.width - 140
                        horizontalAlignment: Text.AlignRight
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Slider {
                    id: assScaleSlider
                    width: parent.width
                    from: 0.5; to: 2.5; stepSize: 0.1
                    value: subtitleSettings.assFontScale
                    focusPolicy: Qt.NoFocus
                    onMoved: subtitleSettings.assFontScale = value
                    background: Rectangle {
                        height: 4; radius: 2; color: Qt.rgba(1, 1, 1, 0.12)
                        Rectangle {
                            width: assScaleSlider.visualPosition * parent.width
                            height: parent.height; radius: 2; color: Theme.accentNeon
                        }
                    }
                    handle: Rectangle {
                        x: assScaleSlider.visualPosition * (assScaleSlider.width - width)
                        y: (assScaleSlider.height - height) / 2
                        width: 13; height: 13; radius: 7; color: "#FFF"
                        border.color: Theme.accentNeon; border.width: 2
                    }
                }
            }

            // ── 텍스트 색상 ──────────────────────────────────
            Column {
                width: parent.width
                spacing: 5
                Text {
                    text: "텍스트 색상 (SRT·SMI·VTT)"
                    color: Qt.rgba(1, 1, 1, 0.6)
                    font.pixelSize: 11; font.family: Theme.fontFamily
                }
                Row {
                    spacing: 6
                    Repeater {
                        model: [
                            { clr: "#FFFFFF", name: "흰색" },
                            { clr: "#FFE234", name: "노란색" },
                            { clr: "#00FFFF", name: "하늘색" },
                            { clr: "#90EE90", name: "연두색" },
                            { clr: "#FF69B4", name: "분홍색" },
                        ]
                        Rectangle {
                            width: 24; height: 24; radius: 5
                            color: modelData.clr
                            border.color: subtitleSettings.textColor === modelData.clr
                                          ? Theme.accentNeon : Qt.rgba(1, 1, 1, 0.25)
                            border.width: subtitleSettings.textColor === modelData.clr ? 2 : 1
                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: subtitleSettings.textColor = modelData.clr
                                ToolTip { text: modelData.name; visible: parent.containsMouse; delay: 300 }
                            }
                        }
                    }
                }
            }

            // ── 배경 불투명도 ─────────────────────────────────
            Column {
                width: parent.width
                spacing: 4
                Row {
                    width: parent.width
                    spacing: 0
                    Text {
                        text: "배경 불투명도"
                        color: Qt.rgba(1, 1, 1, 0.6)
                        font.pixelSize: 11; font.family: Theme.fontFamily
                        width: 140
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: Math.round(subtitleSettings.bgOpacity * 100) + "%"
                        color: Theme.accentNeon
                        font.pixelSize: 11; font.family: Theme.fontFamily
                        width: parent.width - 140
                        horizontalAlignment: Text.AlignRight
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Slider {
                    id: bgOpacitySlider
                    width: parent.width
                    from: 0.0; to: 1.0; stepSize: 0.05
                    value: subtitleSettings.bgOpacity
                    focusPolicy: Qt.NoFocus
                    onMoved: subtitleSettings.bgOpacity = value
                    background: Rectangle {
                        height: 4; radius: 2; color: Qt.rgba(1, 1, 1, 0.12)
                        Rectangle {
                            width: bgOpacitySlider.visualPosition * parent.width
                            height: parent.height; radius: 2; color: Theme.accentNeon
                        }
                    }
                    handle: Rectangle {
                        x: bgOpacitySlider.visualPosition * (bgOpacitySlider.width - width)
                        y: (bgOpacitySlider.height - height) / 2
                        width: 13; height: 13; radius: 7; color: "#FFF"
                        border.color: Theme.accentNeon; border.width: 2
                    }
                }
            }

            // ── 폰트 선택 ─────────────────────────────────────
            Column {
                width: parent.width
                spacing: 5
                Text {
                    text: "폰트 (SRT·SMI·VTT)"
                    color: Qt.rgba(1, 1, 1, 0.6)
                    font.pixelSize: 11; font.family: Theme.fontFamily
                }
                ComboBox {
                    id: fontFamilyCombo
                    width: parent.width
                    focusPolicy: Qt.NoFocus
                    model: [
                        { label: "기본 (테마)",       value: "" },
                        { label: "맑은 고딕",         value: "Malgun Gothic" },
                        { label: "나눔고딕",          value: "NanumGothic" },
                        { label: "나눔명조",          value: "NanumMyeongjo" },
                        { label: "굴림",             value: "Gulim" },
                        { label: "돋움",             value: "Dotum" },
                        { label: "바탕",             value: "Batang" },
                        { label: "Arial",            value: "Arial" },
                        { label: "Times New Roman",  value: "Times New Roman" },
                    ]
                    textRole: "label"
                    currentIndex: {
                        for (var i = 0; i < model.length; i++)
                            if (model[i].value === subtitleSettings.fontFamily) return i
                        return 0
                    }
                    onActivated: subtitleSettings.fontFamily = model[currentIndex].value

                    background: Rectangle {
                        color: Qt.rgba(1, 1, 1, 0.07)
                        radius: 5
                        border.color: Qt.rgba(1, 1, 1, 0.15)
                        border.width: 1
                    }
                    contentItem: Text {
                        leftPadding: 8
                        text: fontFamilyCombo.displayText
                        color: Qt.rgba(1, 1, 1, 0.85)
                        font.pixelSize: 12; font.family: Theme.fontFamily
                        verticalAlignment: Text.AlignVCenter
                    }
                    delegate: ItemDelegate {
                        width: fontFamilyCombo.width
                        contentItem: Text {
                            text: modelData.label
                            color: Qt.rgba(1, 1, 1, 0.85)
                            font.pixelSize: 12
                            font.family: modelData.value !== "" ? modelData.value : Theme.fontFamily
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            color: hovered ? Qt.rgba(0, 168, 255, 0.18) : Qt.rgba(0.1, 0.1, 0.12, 1)
                        }
                    }
                    popup: Popup {
                        y: fontFamilyCombo.height
                        width: fontFamilyCombo.width
                        padding: 0
                        contentItem: ListView {
                            implicitHeight: contentHeight
                            model: fontFamilyCombo.delegateModel
                            clip: true
                        }
                        background: Rectangle {
                            color: Qt.rgba(0.1, 0.1, 0.12, 0.97)
                            radius: 5
                            border.color: Qt.rgba(1, 1, 1, 0.15); border.width: 1
                        }
                    }
                }
            }

            // ── 초기화 버튼 ───────────────────────────────────
            Row {
                width: parent.width
                layoutDirection: Qt.RightToLeft
                Button {
                    flat: true; focusPolicy: Qt.NoFocus
                    contentItem: Text {
                        text: "초기화"
                        color: Qt.rgba(1, 1, 1, 0.4)
                        font.pixelSize: 11; font.family: Theme.fontFamily
                    }
                    background: Rectangle { color: "transparent" }
                    onClicked: {
                        subtitleSettings.plainFontSize = 20
                        subtitleSettings.assFontScale  = 1.0
                        subtitleSettings.fontFamily    = ""
                        subtitleSettings.textColor     = "#FFFFFF"
                        subtitleSettings.bgOpacity     = 0.72
                    }
                }
            }

            Item { height: 0 }
        }
    }

    // ── OSD (즉각 피드백 텍스트) ──────────────────────────────
    Rectangle {
        id: osdRect
        anchors.centerIn: parent
        width: osdText.width + 32; height: 44
        color: Qt.rgba(0, 0, 0, 0.65); radius: 8
        visible: false
        Text {
            id: osdText
            anchors.centerIn: parent
            color: "#FFF"; font.pixelSize: 18
            font.family: Theme.fontFamily
        }
        SequentialAnimation {
            id: osdAnim
            ScriptAction { script: { osdRect.opacity = 1; osdRect.visible = true } }
            PauseAnimation { duration: 1200 }
            NumberAnimation { target: osdRect; property: "opacity"; to: 0; duration: 400 }
            ScriptAction { script: osdRect.visible = false }
        }
    }

    // ── 컨트롤 숨김 타이머 ───────────────────────────────────
    Timer {
        id: controlHideTimer
        interval: 4000; repeat: false
        running: mediaPlayer.playbackState === MediaPlayer.PlayingState && playerRoot.showControls
        onTriggered: playerRoot.showControls = false
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        propagateComposedEvents: true
        onPositionChanged: { playerRoot.showControls = true; controlHideTimer.restart() }
        onClicked: (mouse) => mouse.accepted = false
    }

    // ── 상단 타이틀 바 ───────────────────────────────────────
    Rectangle {
        id: titleBar
        anchors.top: parent.top
        width: parent.width; height: 56
        visible: !playerRoot.isPip
        opacity: (playerRoot.showControls || mediaPlayer.playbackState !== MediaPlayer.PlayingState) ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 250 } }

        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0.85) }
            GradientStop { position: 1.0; color: "transparent" }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left; anchors.leftMargin: 20
            text: playerRoot.title
            color: Qt.rgba(1, 1, 1, 0.85)
            font.pixelSize: 15; font.family: Theme.fontFamily
            elide: Text.ElideRight
            width: parent.width - (playerRoot.videoPlaylist.length > 1 ? 120 : 100)
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: parent.right
            anchors.rightMargin: 24
            visible: playerRoot.videoPlaylist.length > 1
            text: (playerRoot.playlistIndex + 1) + " / " + playerRoot.videoPlaylist.length
            color: Qt.rgba(1, 1, 1, 0.58)
            font.pixelSize: 13
            font.family: Theme.fontFamily
        }
    }

    // ── 하단 컨트롤 바 ───────────────────────────────────────
    Rectangle {
        id: controlBar
        anchors.bottom: parent.bottom
        width: parent.width; height: 150
        visible: !playerRoot.isPip
        opacity: (playerRoot.showControls || mediaPlayer.playbackState !== MediaPlayer.PlayingState) ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 250 } }
        // opacity가 0일 때 클릭 이벤트 차단
        enabled: opacity > 0.05

        gradient: Gradient {
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.92) }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            anchors.bottomMargin: 12
            spacing: 6

            // ── 재생바 ───────────────────────────────────────
            Slider {
                id: progressSlider
                Layout.fillWidth: true
                Layout.preferredHeight: 28
                focusPolicy: Qt.NoFocus
                from: 0; to: Math.max(1, mediaPlayer.duration)
                value: mediaPlayer.position
                onPressedChanged: playerRoot._isUserSeeking = pressed
                onMoved: mediaPlayer.setPosition(value)

                background: Rectangle {
                    color: "transparent"
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: parent.width
                        height: progressSlider.pressed ? 8 : (progressSlider.hovered ? 7 : 5)
                        radius: 4
                        color: Qt.rgba(255, 255, 255, 0.12)
                        Behavior on height { NumberAnimation { duration: 80 } }
                        Rectangle {
                            width: progressSlider.visualPosition * parent.width
                            height: parent.height; radius: parent.radius; color: Theme.accentNeon
                        }
                    }
                }
                handle: Rectangle {
                    x: progressSlider.visualPosition * (progressSlider.width - width)
                    y: (progressSlider.height - height) / 2
                    width: 14; height: 14; radius: 7; color: "#FFF"
                    border.color: Theme.accentNeon; border.width: 2
                    visible: progressSlider.hovered || progressSlider.pressed
                    scale: progressSlider.hovered ? 1.2 : 1.0
                    Behavior on scale { NumberAnimation { duration: 100 } }
                }
            }

            // ── 버튼 행 ─────────────────────────────────────
            RowLayout {
                spacing: 10
                Layout.minimumHeight: playerRoot.playerVolIconBox + 8

                // 재생/일시정지
                Button {
                    id: playPauseBtn
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerBarPlayPx
                    topPadding: 4
                    bottomPadding: 4
                    onClicked: mediaPlayer.playbackState === MediaPlayer.PlayingState
                        ? mediaPlayer.pause() : mediaPlayer.play()
                    contentItem: Text {
                        text: mediaPlayer.playbackState === MediaPlayer.PlayingState ? "" : ""
                        color: "#FFF"
                        font.pixelSize: playPauseBtn.font.pixelSize
                        font.family: Theme.iconFont
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle { color: "transparent" }
                    scale: playPauseBtn.hovered ? 1.15 : 1.0
                    Behavior on scale { NumberAnimation { duration: 100 } }
                }

                // 시간
                Text {
                    Layout.alignment: Qt.AlignVCenter
                    text: formatTime(mediaPlayer.position) + " / " + formatTime(mediaPlayer.duration)
                    color: Qt.rgba(1, 1, 1, 0.75)
                    font.pixelSize: 14
                    font.family: Theme.fontFamily
                }

                // 10초 뒤로
                Button {
                    id: seekBackBtn
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerSeekIconPx
                    topPadding: 4
                    bottomPadding: 4
                    contentItem: Text {
                        text: ""
                        color: "#FFF"
                        font.pixelSize: seekBackBtn.font.pixelSize
                        font.family: Theme.iconFont
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle { color: "transparent" }
                    onClicked: mediaPlayer.setPosition(Math.max(0, mediaPlayer.position - 10000))
                    ToolTip { text: "10초 뒤로 (←)"; visible: parent.hovered; delay: 500 }
                }

                // 10초 앞으로
                Button {
                    id: seekFwdBtn
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerSeekIconPx
                    topPadding: 4
                    bottomPadding: 4
                    contentItem: Text {
                        text: ""
                        color: "#FFF"
                        font.pixelSize: seekFwdBtn.font.pixelSize
                        font.family: Theme.iconFont
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle { color: "transparent" }
                    onClicked: mediaPlayer.setPosition(Math.min(mediaPlayer.duration, mediaPlayer.position + 10000))
                    ToolTip { text: "10초 앞으로 (→)"; visible: parent.hovered; delay: 500 }
                }

                Item { Layout.fillWidth: true }

                // ── 자막 선택 ────────────────────────────────
                Row {
                    spacing: 4
                    visible: playerRoot.subtitleTracks.length > 0
                    Layout.alignment: Qt.AlignVCenter

                    Text {
                        text: "자막:"
                        color: Qt.rgba(1, 1, 1, 0.65)
                        font.pixelSize: 14
                        font.family: Theme.fontFamily
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Repeater {
                        model: playerRoot.subtitleTracks

                        Button {
                            flat: true
                            focusPolicy: Qt.NoFocus
                            text: modelData.label
                            font.pixelSize: 13
                            topPadding: 4
                            bottomPadding: 4
                            checked: playerRoot.activeSubtitleIdx === index
                            contentItem: Text {
                                text: parent.text
                                color: parent.checked ? Theme.accentNeon : Qt.rgba(1, 1, 1, 0.6)
                                font: parent.font
                                verticalAlignment: Text.AlignVCenter
                            }
                            background: Rectangle {
                                color: parent.checked ? Qt.rgba(0, 168, 255, 0.15) : "transparent"
                                radius: 4
                                border.color: parent.checked ? Theme.accentNeon : "transparent"
                                border.width: 1
                            }
                            onClicked: {
                                if (playerRoot.activeSubtitleIdx === index)
                                    playerRoot.loadSubtitle(-1)
                                else
                                    playerRoot.loadSubtitle(index)
                            }
                        }
                    }

                    // 자막 끄기
                    Button {
                        flat: true
                        focusPolicy: Qt.NoFocus
                        font.pixelSize: 13
                        topPadding: 4
                        bottomPadding: 4
                        visible: playerRoot.activeSubtitleIdx >= 0
                        contentItem: Text {
                            text: "OFF"
                            color: Qt.rgba(1, 1, 1, 0.5)
                            font: parent.font
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle { color: "transparent" }
                        onClicked: playerRoot.loadSubtitle(-1)
                    }

                }

                // 자막 글꼴·크기 설정 (항상 표시)
                Button {
                    id: subtitleSettingBtn
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerBarIconPx
                    topPadding: 4
                    bottomPadding: 4
                    leftPadding: 6
                    rightPadding: 6
                    contentItem: Text {
                        text: ""
                        color: subtitleSettingsPopup.visible
                               ? Theme.accentNeon : Qt.rgba(1, 1, 1, 0.55)
                        font.pixelSize: subtitleSettingBtn.font.pixelSize
                        font.family: Theme.iconFont
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        color: subtitleSettingsPopup.visible
                               ? Qt.rgba(0, 168, 255, 0.12) : "transparent"
                        radius: 4
                        border.color: subtitleSettingsPopup.visible
                                      ? Theme.accentNeon : "transparent"
                        border.width: 1
                    }
                    onClicked: {
                        if (subtitleSettingsPopup.visible) {
                            subtitleSettingsPopup.close()
                        } else {
                            var pt = subtitleSettingBtn.mapToItem(playerRoot, 0, 0)
                            subtitleSettingsPopup.x = Math.max(4,
                                Math.min(pt.x, playerRoot.width - subtitleSettingsPopup.width - 4))
                            subtitleSettingsPopup.y = pt.y - subtitleSettingsPopup.height - 10
                            subtitleSettingsPopup.open()
                        }
                    }
                    ToolTip { text: "자막 글꼴·크기·색상"; visible: parent.hovered; delay: 500 }
                }

                // ── 별점 ─────────────────────────────────────
                RatingWidget {
                    id: ratingWidget
                    rating: PlayerModel.currentRating
                    starSize: playerRoot.playerStarSize
                    Layout.alignment: Qt.AlignVCenter
                    onRatingSelected: function(r) {
                        PlayerModel.setRating(playerRoot.productCode, r)
                        window.showToast(r > 0 ? "별점 " + r + "점 저장!" : "별점 초기화", "success")
                    }
                }

                // 좋아요
                Button {
                    id: likeBtn
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerBarIconPx
                    topPadding: 4
                    bottomPadding: 4
                    property bool active: PlayerModel.isLiked
                    contentItem: Text {
                        text: ""
                        font.pixelSize: likeBtn.font.pixelSize
                        font.family: Theme.iconFont
                        color: likeBtn.active ? "#FF4081" : Qt.rgba(1, 1, 1, 0.45)
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }
                    background: Rectangle { color: "transparent" }
                    scale: likeBtn.hovered ? 1.2 : (likeBtn.active ? 1.1 : 1.0)
                    Behavior on scale { NumberAnimation { duration: 120 } }
                    onClicked: {
                        PlayerModel.setLike(playerRoot.productCode)
                        window.showToast(PlayerModel.isLiked ? "좋아요 ❤" : "좋아요 취소", PlayerModel.isLiked ? "success" : "info")
                    }
                    ToolTip { text: "좋아요"; visible: parent.hovered; delay: 500 }
                }

                // 싫어요
                Button {
                    id: dislikeBtn
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerBarIconPx
                    topPadding: 4
                    bottomPadding: 4
                    property bool active: PlayerModel.isDisliked
                    contentItem: Text {
                        text: ""
                        font.pixelSize: dislikeBtn.font.pixelSize
                        font.family: Theme.iconFont
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment: Text.AlignHCenter
                        color: dislikeBtn.active ? "#FF6B6B" : Qt.rgba(1, 1, 1, 0.45)
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }
                    background: Rectangle { color: "transparent" }
                    scale: dislikeBtn.hovered ? 1.2 : (dislikeBtn.active ? 1.1 : 1.0)
                    Behavior on scale { NumberAnimation { duration: 120 } }
                    onClicked: {
                        PlayerModel.setDislike(playerRoot.productCode)
                        window.showToast(PlayerModel.isDisliked ? "취향에서 제외됩니다" : "싫어요 취소", "warning")
                    }
                    ToolTip { text: "싫어요"; visible: parent.hovered; delay: 500 }
                }

                Row {
                    id: volumeControlRow
                    spacing: 6
                    height: playerRoot.playerVolIconBox
                    Layout.alignment: Qt.AlignVCenter
                    Layout.minimumWidth: playerRoot.playerVolIconBox + 6 + playerRoot.playerVolSliderW
                    Layout.preferredWidth: playerRoot.playerVolIconBox + 6 + playerRoot.playerVolSliderW

                    Rectangle {
                        id: volIconBox
                        width: playerRoot.playerVolIconBox
                        height: playerRoot.playerVolIconBox
                        radius: 6
                        color: volIconMa.containsMouse ? Qt.rgba(255, 255, 255, 0.10) : "transparent"
                        border.color: volIconMa.containsMouse ? Qt.rgba(255, 255, 255, 0.18) : "transparent"
                        border.width: 1

                        Text {
                            anchors.centerIn: parent
                            text: audioOutput.muted ? "" : ""
                            color: "#FFF"
                            font.pixelSize: playerRoot.playerBarIconPx
                            font.family: Theme.iconFont
                        }

                        MouseArea {
                            id: volIconMa
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: {
                                audioOutput.muted = !audioOutput.muted
                                showOsd(audioOutput.muted ? "🔇  음소거" : "🔊  음소거 해제")
                            }
                        }
                        ToolTip { text: audioOutput.muted ? "음소거 해제 (M)" : "음소거 (M)"; visible: volIconMa.containsMouse; delay: 500 }
                    }
                    Slider {
                        id: volumeSlider
                        width: playerRoot.playerVolSliderW
                        height: volumeControlRow.height
                        from: 0
                        to: 1.0
                        focusPolicy: Qt.NoFocus
                        value: playerSettings.volume
                        onValueChanged: playerSettings.volume = value

                        // Qt Slider는 background 높이만 쓰면 위쪽에 붙고, 핸들은 전체 높이 기준 중앙이라 어긋남 → 트랙을 Row 높이 안에서 수직 중앙에 둔다.
                        background: Item {
                            implicitWidth: playerRoot.playerVolSliderW
                            implicitHeight: volumeControlRow.height

                            Rectangle {
                                id: volSliderTrack
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width
                                height: 5
                                radius: 2
                                color: Qt.rgba(1, 1, 1, 0.15)
                                Rectangle {
                                    anchors.left: parent.left
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: parent.height
                                    width: volumeSlider.visualPosition * parent.width
                                    radius: volSliderTrack.radius
                                    color: Theme.accentNeon
                                }
                            }
                        }
                        handle: Rectangle {
                            x: volumeSlider.visualPosition * (volumeSlider.width - width)
                            y: (volumeSlider.height - height) / 2
                            width: 15; height: 15; radius: 8
                            color: "#FFF"
                            border.color: Theme.accentNeon; border.width: 1
                        }
                    }
                }

                // PIP 토글
                Button {
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerBarIconPx
                    topPadding: 4
                    bottomPadding: 4
                    contentItem: Text {
                        text: ""
                        color: playerRoot.isPip ? Theme.accentNeon : Qt.rgba(1, 1, 1, 0.7)
                        font.pixelSize: parent.font.pixelSize
                        font.family: Theme.iconFont
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle { color: "transparent" }
                    onClicked: playerRoot.isPip = !playerRoot.isPip
                    ToolTip { text: "PIP 모드 (P)"; visible: parent.hovered; delay: 500 }
                }

                // 전체화면 토글
                Button {
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerBarIconPx
                    topPadding: 4
                    bottomPadding: 4
                    contentItem: Text {
                        text: playerRoot.isFullscreen ? "" : ""
                        color: Qt.rgba(1, 1, 1, 0.7)
                        font.pixelSize: parent.font.pixelSize
                        font.family: Theme.iconFont
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle { color: "transparent" }
                    onClicked: playerRoot._toggleFullscreen()
                    ToolTip { text: playerRoot.isFullscreen ? "전체화면 해제 (F/Enter)" : "전체화면 (F/Enter)"; visible: parent.hovered; delay: 500 }
                }

                // 닫기
                Button {
                    flat: true
                    focusPolicy: Qt.NoFocus
                    Layout.alignment: Qt.AlignVCenter
                    font.pixelSize: playerRoot.playerBarIconPx
                    topPadding: 4
                    bottomPadding: 4
                    contentItem: Text {
                        text: ""
                        color: Qt.rgba(1, 1, 1, 0.7)
                        font.pixelSize: parent.font.pixelSize
                        font.family: Theme.iconFont
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        color: parent.hovered ? Qt.rgba(1, 0, 0, 0.25) : "transparent"
                        radius: 5
                        Behavior on color { ColorAnimation { duration: 150 } }
                    }
                    onClicked: playerRoot._closePlayer()
                    ToolTip { text: "닫기 (Esc)"; visible: parent.hovered; delay: 500 }
                }
            }
        }
    }

    // ── 시그널 & 초기화 ──────────────────────────────────────
    signal closeRequest()

    function videoLocalPathFromSource() {
        var vidStr = playerRoot.videoSource.toString()
        if (!vidStr)
            return ""
        vidStr = vidStr.replace(/^file:\/\/\//, "").replace(/^file:\/\//, "")
        try { vidStr = decodeURIComponent(vidStr) } catch (e1) {}
        return vidStr
    }

    function reloadSubtitleTracks() {
        playerRoot.loadSubtitle(-1)
        playerRoot.subtitleTracks = []
        var vidStr = playerRoot.currentVideoFilePath || playerRoot.videoLocalPathFromSource()
        if (!vidStr)
            return
        var tracksJson = PlayerModel.findSubtitleFiles(vidStr)
        try {
            playerRoot.subtitleTracks = JSON.parse(tracksJson)
            var pickedKo = false
            for (var i = 0; i < playerRoot.subtitleTracks.length; i++) {
                if (playerRoot.subtitleTracks[i].filename.indexOf(".ko.") >= 0) {
                    playerRoot.loadSubtitle(i)
                    pickedKo = true
                    break
                }
            }
            if (!pickedKo && playerRoot.subtitleTracks.length > 0)
                playerRoot.loadSubtitle(0)
        } catch (e2) {}
    }

    function formatTime(ms) {
        if (ms <= 0) return "0:00"
        var totalSec = Math.floor(ms / 1000)
        var h = Math.floor(totalSec / 3600)
        var m = Math.floor((totalSec % 3600) / 60)
        var s = totalSec % 60
        var mm = m < 10 ? "0" + m : m
        var ss = s < 10 ? "0" + s : s
        return h > 0 ? h + ":" + mm + ":" + ss : m + ":" + ss
    }

    Component.onCompleted: {
        bgRect.state = "visible"
        playerRoot.state = "normal"
        playerRoot.forceActiveFocus()
        // productCode는 Qt.callLater로 나중에 주입됨 → onProductCodeChanged에서 초기화
    }

    // productCode가 실제로 세팅된 시점에 DB에서 별점·좋아요 로드
    onProductCodeChanged: {
        if (productCode) {
            PlayerModel.startWatch(productCode, 0)
            ratingWidget.rating = PlayerModel.getRatingForProduct(productCode)
        }
    }

    Connections {
        target: PlayerModel
        function onRatingChanged(r) { ratingWidget.rating = r }
        function onLikeStateChanged(liked, disliked) {}
        function onPlaybackProxyReady(originalPath, proxyPath) {
            if (!originalPath || originalPath !== playerRoot.currentVideoFilePath)
                return
            var pos = mediaPlayer.position
            if (pos > 0)
                playerRoot.resumePosition = pos
            playerRoot._seekDone = false
            playerRoot._prevPosition = 0
            playerRoot._autoPlayPending = true
            playerRoot.videoSource = Theme.pathToUrl(proxyPath)
            showOsd("재생용 MP4 프록시로 전환")
        }
    }
}
