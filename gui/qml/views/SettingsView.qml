import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

Item {
    id: root

    Popup {
        id: similarPopup
        modal: true
        dim: true
        focus: true
        padding: Theme.spacingMd
        parent: Overlay.overlay
        anchors.centerIn: Overlay.overlay
        width: Math.min(520, Overlay.overlay ? (Overlay.overlay.width - 48) : 520)
        z: 260

        property string headerText: ""
        property string bodyText: ""

        background: Rectangle {
            radius: Theme.radiusMd
            color: Theme.bgSecondary
            border.color: Theme.glassBorder
            border.width: 1
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.spacingSm

            Text {
                text: similarPopup.headerText
                font.pixelSize: Theme.fontSubtitle
                font.weight: Font.DemiBold
                color: Theme.textPrimary
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            AppScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: 320
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                TextArea {
                    text: similarPopup.bodyText
                    readOnly: true
                    wrapMode: TextEdit.NoWrap
                    selectByMouse: true
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontBody
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.surfaceLight
                        border.color: Theme.glassBorder
                        border.width: 1
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "닫기"
                    primary: true
                    neonGlow: true
                    onClicked: similarPopup.close()
                }
            }
        }
    }

    Popup {
        id: genreSelectionPopup
        modal: true
        dim: true
        focus: true
        padding: Theme.spacingMd
        parent: Overlay.overlay
        anchors.centerIn: Overlay.overlay
        width: Math.min(400, Overlay.overlay ? (Overlay.overlay.width - 48) : 400)
        height: Math.min(600, Overlay.overlay ? (Overlay.overlay.height - 48) : 600)
        z: 261

        background: Rectangle {
            radius: Theme.radiusMd
            color: Theme.bgSecondary
            border.color: Theme.glassBorder
            border.width: 1
        }

        property var selectedSet: ({})

        function openWith(currentCsv) {
            var s = {}
            var parts = (currentCsv || "").split(",")
            for (var i=0; i<parts.length; i++) {
                var p = parts[i].trim()
                if (p) s[p] = true
            }
            selectedSet = s
            genreSearchField.text = ""
            open()
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.spacingSm

            Text {
                text: "제외할 장르 선택"
                font.pixelSize: Theme.fontSubtitle
                font.weight: Font.DemiBold
                color: Theme.textPrimary
            }

            TextField {
                id: genreSearchField
                Layout.fillWidth: true
                placeholderText: "장르 검색..."
                color: Theme.textPrimary
                font.pixelSize: Theme.fontBody
                background: Rectangle {
                    radius: Theme.radiusSm
                    color: Theme.surfaceLight
                    border.color: parent.activeFocus ? Theme.accentNeon : Theme.glassBorder
                    border.width: 1
                }
            }

            ListView {
                boundsBehavior: Theme.boundsBehavior
                id: genreList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: {
                    var all = SettingsModel.allGenres || []
                    var query = (genreSearchField.text || "").toLowerCase()
                    if (!query) return all
                    return all.filter(function(g) { return (g || "").toLowerCase().indexOf(query) !== -1 })
                }
                delegate: RowLayout {
                    width: genreList.width
                    spacing: Theme.spacingSm
                    CheckBox {
                        id: cb
                        checked: !!genreSelectionPopup.selectedSet[modelData]
                        onToggled: {
                            var s = genreSelectionPopup.selectedSet
                            if (checked) s[modelData] = true
                            else delete s[modelData]
                            genreSelectionPopup.selectedSet = s
                        }
                    }
                    Text {
                        text: modelData
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontBody
                        Layout.fillWidth: true
                        MouseArea {
                            anchors.fill: parent
                            onClicked: cb.toggle()
                        }
                    }
                }
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }

            RowLayout {
                Layout.fillWidth: true
                ActionButton {
                    text: "취소"
                    onClicked: genreSelectionPopup.close()
                }
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: "적용"
                    primary: true
                    onClicked: {
                        var keys = Object.keys(genreSelectionPopup.selectedSet)
                        SettingsModel.excludedGenres = keys.join(",")
                        genreSelectionPopup.close()
                    }
                }
            }
        }
    }


    Connections {
        target: SettingsModel
        function onToastMessage(msg, level) { window.showToast(msg, level); }
        function onSimilarEmbeddingsReady(productCode, model, text) {
            similarPopup.headerText = "유사작 Top10 — " + (productCode || "") + " (model=" + (model || "") + ")"
            similarPopup.bodyText = text || ""
            similarPopup.open()
        }
    }
    Connections {
        target: LibraryModel
        function onToastMessage(msg, level) { window.showToast(msg, level); }
    }

    AppScrollView {
        id: scrollView
        anchors.fill: parent
        anchors.margins: Theme.spacingLg
        contentWidth: availableWidth

        Column {
            width: parent.width
            spacing: Theme.spacingLg

            // ── 헤더 ────────────────────────────────────
            Text {
                text: "설정"
                font.pixelSize: Theme.fontTitle
                font.weight: Font.ExtraBold
                color: Theme.textPrimary
            }

            // ── API 설정 ────────────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "API 설정"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    // OpenRouter API 키
                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "OpenRouter API 키"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TextField {
                            id: apiKeyField
                            width: parent.width - 180
                            echoMode: TextInput.Password
                            text: SettingsModel.apiKey
                            onTextChanged: SettingsModel.apiKey = text
                            placeholderText: "sk-or-v1-..."
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: apiKeyField.activeFocus ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    // Gemini API 키
                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "Gemini API 키"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TextField {
                            id: geminiKeyField
                            width: parent.width - 180
                            echoMode: TextInput.Password
                            text: SettingsModel.geminiApiKey
                            onTextChanged: SettingsModel.geminiApiKey = text
                            placeholderText: "AIza..."
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: geminiKeyField.activeFocus ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    // Ollama URL
                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "Ollama URL"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TextField {
                            id: ollamaField
                            width: parent.width - 180
                            text: SettingsModel.ollamaUrl
                            onTextChanged: SettingsModel.ollamaUrl = text
                            placeholderText: "http://localhost:11434"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: ollamaField.activeFocus ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    Row {
                        layoutDirection: Qt.RightToLeft
                        width: parent.width
                        ActionButton {
                            text: "API 키 저장"
                            onClicked: SettingsModel.saveApiKey()
                        }
                    }
                }
            }

            // ── 데이터 경로 ─────────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "데이터 경로"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "미디어 루트"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TextField {
                            id: mediaField
                            width: parent.width - 220
                            text: SettingsModel.mediaRoot
                            onTextChanged: SettingsModel.mediaRoot = text
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: mediaField.activeFocus ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1
                            }
                        }
                        ActionButton {
                            text: "..."
                            primary: false
                            onClicked: {
                                var p = SettingsModel.browseFolder();
                                if (p) { SettingsModel.mediaRoot = p; mediaField.text = p; }
                            }
                        }
                    }

                    Row {
                        layoutDirection: Qt.RightToLeft
                        width: parent.width
                        ActionButton {
                            text: "경로 저장"
                            onClicked: SettingsModel.savePaths()
                        }
                    }
                }
            }

            // ── DB 재동기화 ─────────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "DB 재동기화"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    Text {
                        text: "마스터 매핑(장르/배우/메이커) 기준으로 작품 메타의 한국어 필드(및 레거시 필드)를 일괄 갱신합니다.\\n이미 한국어로 보이는 값은 건드리지 않습니다."
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        wrapMode: Text.WordWrap
                        width: parent.width
                    }

                    Row {
                        layoutDirection: Qt.RightToLeft
                        width: parent.width
                        ActionButton {
                            text: "메타데이터 재동기화 실행"
                            primary: false
                            onClicked: LibraryModel.resyncMetadataKo()
                        }
                    }
                }
            }

            // ── 외관 ────────────────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "외관"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    Row {
                        spacing: Theme.spacingSm

                        Repeater {
                            model: ["Win11", "Light", "Dark"]

                            Rectangle {
                                width: 80; height: 36
                                radius: Theme.radiusSm
                                color: SettingsModel.themeMode === index ? Theme.primaryBlue : Theme.surfaceLight
                                border.color: SettingsModel.themeMode === index ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1

                                Text {
                                    anchors.centerIn: parent
                                    text: modelData
                                    font.pixelSize: Theme.fontCaption
                                    font.weight: Font.DemiBold
                                    color: SettingsModel.themeMode === index ? (Theme.isDark ? "#0A0E1A" : "#FFFFFF") : Theme.textSecondary
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: SettingsModel.themeMode = index
                                }
                            }
                        }
                    }
                }
            }

            // ── STT 모델 ────────────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "STT (음성 인식)"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    Row {
                        spacing: Theme.spacingSm

                        Text {
                            text: "Whisper 모델"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        ComboBox {
                            id: whisperCombo
                            model: ["large-v2", "large-v3", "medium", "small", "turbo"]
                            width: 200
                            currentIndex: {
                                var m = {"large-v2":0,"large-v3":1,"medium":2,"small":3,"turbo":4};
                                return m[SettingsModel.whisperModel] || 0;
                            }
                            onCurrentIndexChanged: {
                                var models = ["large-v2","large-v3","medium","small","turbo"];
                                SettingsModel.whisperModel = models[currentIndex];
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: whisperCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }
                }
            }

            // ── 번역 프로필 ─────────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "한국어 번역"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    Row {
                        spacing: Theme.spacingSm

                        Text {
                            text: "번역 프로필"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        ComboBox {
                            id: profileCombo
                            model: [
                                "DeepSeek V3.2",
                                "GLM 5.1",
                                "DeepSeek V3 Chat",
                                "Gemini 3 Flash",
                                "Gemini 3 Flash Lite",
                                "Gemini 2.5 Flash",
                                "Gemini 2.5 Pro",
                                "Gemini 2 Flash",
                                "Gemini 2 Flash Lite",
                                "Gemma4 E4B (Local)",
                                "Qwen 3.5 9B (Local)",
                                "Qwen 3 14B (Local)",
                                "Gemma 3 12B (Local)",
                                "Gemma 2 9B (Local)",
                                "Qwen 2.5 7B (Local)",
                                "JKV-12B (Local)"
                            ]
                            width: 200
                            currentIndex: {
                                var m = {
                                    "default": 0,
                                    "keeper": 1,
                                    "deepseek_chat": 2,
                                    "gemini_3_flash": 3,
                                    "gemini_3_flash_lite": 4,
                                    "gemini_25_flash": 5,
                                    "gemini_25_pro": 6,
                                    "gemini_2_flash": 7,
                                    "gemini_2_flash_lite": 8,
                                    "budget": 9,
                                    "qwen35": 10,
                                    "qwen3_14": 11,
                                    "gemma3_12": 12,
                                    "gemma2_9": 13,
                                    "qwen25_7": 14,
                                    "jkv_12b": 15
                                };
                                return m[SettingsModel.translationProfile] !== undefined ? m[SettingsModel.translationProfile] : 0;
                            }
                            onCurrentIndexChanged: {
                                var profiles = [
                                    "default",
                                    "keeper",
                                    "deepseek_chat",
                                    "gemini_3_flash",
                                    "gemini_3_flash_lite",
                                    "gemini_25_flash",
                                    "gemini_25_pro",
                                    "gemini_2_flash",
                                    "gemini_2_flash_lite",
                                    "budget",
                                    "qwen35",
                                    "qwen3_14",
                                    "gemma3_12",
                                    "gemma2_9",
                                    "qwen25_7",
                                    "jkv_12b"
                                ];
                                SettingsModel.translationProfile = profiles[currentIndex];
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: profileCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }

                    // ── 크롤링(수집) 다국어 번역 모델 ─────────────────
                    Row {
                        spacing: Theme.spacingSm

                        Text {
                            text: "크롤링 번역 모델"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        ComboBox {
                            id: harvestTransCombo
                            model: [
                                "DeepSeek V3.2 (OpenRouter)",
                                "Gemini 3 Flash",
                                "Gemini 3 Flash Lite",
                                "Gemini 2.5 Flash",
                                "Gemini 2.5 Pro",
                                "Gemini 2 Flash",
                                "Gemini 2 Flash Lite",
                                "Gemma4:E4B (Local)",
                                "Qwen2.4:14B (Local)",
                                "Gemma 3:12B (Local)",
                                "Gemma 2:9B (Local)",
                                "Qwen 2.5:7B (Local)",
                                "JKV-12B (Local)"
                            ]
                            width: 220
                            currentIndex: {
                                var v = (SettingsModel.harvestTranslationModel || "").toLowerCase()
                                var m = {
                                    "openrouter:deepseek/deepseek-v3.2": 0,
                                    "gemini:gemini-3.0-flash": 1,
                                    "gemini:gemini-3.1-flash-lite": 2,
                                    "gemini:gemini-2.5-flash": 3,
                                    "gemini:gemini-2.5-pro": 4,
                                    "gemini:gemini-2.0-flash": 5,
                                    "gemini:gemini-2.0-flash-lite": 6,
                                    "ollama:gemma4:e4b": 7,
                                    "ollama:qwen2.4:14b": 8,
                                    "ollama:gemma3:12b": 9,
                                    "ollama:gemma2:9b": 10,
                                    "ollama:qwen2.5:7b": 11,
                                    "ollama:ja-ko-vn-jav:latest": 12
                                }
                                return m[v] !== undefined ? m[v] : 0
                            }
                            onCurrentIndexChanged: {
                                var vals = [
                                    "openrouter:deepseek/deepseek-v3.2",
                                    "gemini:gemini-3.0-flash",
                                    "gemini:gemini-3.1-flash-lite",
                                    "gemini:gemini-2.5-flash",
                                    "gemini:gemini-2.5-pro",
                                    "gemini:gemini-2.0-flash",
                                    "gemini:gemini-2.0-flash-lite",
                                    "ollama:gemma4:e4b",
                                    "ollama:qwen2.4:14b",
                                    "ollama:gemma3:12b",
                                    "ollama:gemma2:9b",
                                    "ollama:qwen2.5:7b",
                                    "ollama:ja-ko-vn-jav:latest"
                                ]
                                SettingsModel.harvestTranslationModel = vals[currentIndex] || vals[0]
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: harvestTransCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }

                    // ── [추가] 정밀 교정 LLM ──
                    Row {
                        spacing: Theme.spacingSm
                        Text {
                            text: "정밀 교정 LLM"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ComboBox {
                            id: correctionCombo
                            model: [
                                "Qwen 3 235B (OpenRouter)",
                                "DeepSeek V3.2 (OpenRouter)",
                                "GLM 5.1 (OpenRouter)",
                                "Gemini 3 Flash",
                                "Gemini 3 Flash Lite",
                                "Gemini 2.5 Flash",
                                "Gemini 2.5 Pro",
                                "Gemini 2 Flash",
                                "Gemini 2 Flash Lite"
                            ]
                            width: 200
                            enabled: !SettingsModel.correctionSkip
                            currentIndex: {
                                var m = {
                                    "qwen/qwen3-235b-a22b-2507": 0,
                                    "deepseek/deepseek-v3.2": 1,
                                    "z-ai/glm-5.1": 2,
                                    "gemini:gemini-3.0-flash": 3,
                                    "gemini:gemini-3.1-flash-lite": 4,
                                    "gemini:gemini-2.5-flash": 5,
                                    "gemini:gemini-2.5-pro": 6,
                                    "gemini:gemini-2.0-flash": 7,
                                    "gemini:gemini-2.0-flash-lite": 8
                                };
                                return m[SettingsModel.correctionProfile] !== undefined ? m[SettingsModel.correctionProfile] : 0;
                            }
                            onCurrentIndexChanged: {
                                var models = [
                                    "qwen/qwen3-235b-a22b-2507",
                                    "deepseek/deepseek-v3.2",
                                    "z-ai/glm-5.1",
                                    "gemini:gemini-3.0-flash",
                                    "gemini:gemini-3.1-flash-lite",
                                    "gemini:gemini-2.5-flash",
                                    "gemini:gemini-2.5-pro",
                                    "gemini:gemini-2.0-flash",
                                    "gemini:gemini-2.0-flash-lite"
                                ];
                                SettingsModel.correctionProfile = models[currentIndex];
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                                opacity: parent.enabled ? 1.0 : 0.5
                            }
                            contentItem: Text {
                                text: correctionCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                                opacity: parent.enabled ? 1.0 : 0.5
                            }
                        }

                        Row {
                            spacing: Theme.spacingXs
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                text: "교정 건너뛰기"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textSecondary
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Switch {
                                id: correctionSkipSwitch
                                checked: SettingsModel.correctionSkip
                                onToggled: SettingsModel.correctionSkip = checked
                                
                                indicator: Rectangle {
                                    implicitWidth: 32
                                    implicitHeight: 16
                                    radius: 8
                                    color: correctionSkipSwitch.checked ? Theme.accentNeon : Theme.surfaceLight
                                    border.color: correctionSkipSwitch.checked ? Theme.accentNeon : Theme.glassBorder
                                    border.width: 1

                                    Rectangle {
                                        x: correctionSkipSwitch.checked ? parent.width - width - 2 : 2
                                        y: 2
                                        width: 12
                                        height: 12
                                        radius: 6
                                        color: "white"
                                        Behavior on x { NumberAnimation { duration: 150 } }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── 기타 옵션 ───────────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "기타 옵션"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    // ── 임베딩 옵션 ─────────────────────────
                    Row {
                        spacing: Theme.spacingSm
                        Text {
                            text: "Ollama 임베딩"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Switch {
                            id: embedSwitch
                            checked: SettingsModel.embeddingsEnabled
                            onToggled: SettingsModel.embeddingsEnabled = checked

                            indicator: Rectangle {
                                implicitWidth: 40
                                implicitHeight: 20
                                x: embedSwitch.leftPadding
                                y: parent.height / 2 - height / 2
                                radius: 10
                                color: embedSwitch.checked ? Theme.accentNeon : Theme.surfaceLight
                                border.color: embedSwitch.checked ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1

                                Rectangle {
                                    x: embedSwitch.checked ? parent.width - width - 2 : 2
                                    y: 2
                                    width: 16
                                    height: 16
                                    radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }
                    }

                    Text {
                        text: "메타+캐노니컬+자막을 합쳐 data/cache/embeddings/ 에 벡터 캐시를 생성합니다."
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        leftPadding: 168
                        wrapMode: Text.Wrap
                        width: parent.width
                    }

                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "임베딩 모델"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TextField {
                            id: embedModelField
                            width: 260
                            text: SettingsModel.embeddingsOllamaModel
                            onTextChanged: SettingsModel.embeddingsOllamaModel = text
                            placeholderText: "nomic-embed-text"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: embedModelField.activeFocus ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1
                            }
                        }
                    }

                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "제외할 장르 태그"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TextField {
                            id: excludedGenresField
                            width: parent.width - 260
                            text: SettingsModel.excludedGenres
                            onTextChanged: SettingsModel.excludedGenres = text
                            placeholderText: "쉼표로 구분 (예: 단독작품,독점...)"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: excludedGenresField.activeFocus ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1
                            }
                        }
                        ActionButton {
                            text: "선택..."
                            primary: false
                            onClicked: genreSelectionPopup.openWith(SettingsModel.excludedGenres)
                        }
                    }

                    Text {
                        text: "유사도 분석 및 인사이트 선호 장르 TOP 8에서 제외할 태그입니다. (예: 단독작품, 독점, 검열 완료)"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        leftPadding: 168
                        wrapMode: Text.Wrap
                        width: parent.width
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }


                    // ── 임베딩 수동 실행 ─────────────────────
                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "수동 실행 품번"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        TextField {
                            id: embedProductField
                            width: 200
                            placeholderText: "ABC-123"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontBody
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: embedProductField.activeFocus ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1
                            }
                        }
                        ActionButton {
                            text: "생성"
                            primary: false
                            onClicked: SettingsModel.runEmbeddings(embedProductField.text, false)
                        }
                        ActionButton {
                            text: "강제 재생성"
                            primary: false
                            onClicked: SettingsModel.runEmbeddings(embedProductField.text, true)
                        }
                        ActionButton {
                            text: "유사작 Top10"
                            primary: false
                            onClicked: SettingsModel.findSimilarEmbeddings(embedProductField.text)
                        }
                    }

                    Row {
                        spacing: Theme.spacingSm
                        Text {
                            text: "Harvest 동시 실행"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        ComboBox {
                            id: harvestConcCombo
                            model: ["1", "2", "3", "4", "5"]
                            width: 120
                            currentIndex: Math.max(0, Math.min(4, (SettingsModel.harvestConcurrency || 2) - 1))
                            onCurrentIndexChanged: {
                                var vals = [1,2,3,4,5];
                                SettingsModel.harvestConcurrency = vals[currentIndex] || 2;
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: harvestConcCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }

                    Text {
                        text: "권장 2~3, 고성능 환경은 5 (OpenRouter 요청/DB 부하 증가)"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        leftPadding: 168
                    }

                    Row {
                        spacing: Theme.spacingSm
                        Text {
                            text: "Grok 스토리 맥락"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Switch {
                            id: grokSwitch
                            checked: SettingsModel.grokEnabled
                            onToggled: SettingsModel.grokEnabled = checked
                            
                            indicator: Rectangle {
                                implicitWidth: 40
                                implicitHeight: 20
                                x: grokSwitch.leftPadding
                                y: parent.height / 2 - height / 2
                                radius: 10
                                color: grokSwitch.checked ? Theme.accentNeon : Theme.surfaceLight
                                border.color: grokSwitch.checked ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1

                                Rectangle {
                                    x: grokSwitch.checked ? parent.width - width - 2 : 2
                                    y: 2
                                    width: 16
                                    height: 16
                                    radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }
                    }

                    Text {
                        text: "Harvest 후 Grok API로 스토리 컨텍스트 캐시 생성"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        leftPadding: 168
                    }

                    Rectangle {
                        width: parent.width; height: 1
                        color: Theme.glassBorder
                    }

                    Row {
                        spacing: Theme.spacingSm
                        Text {
                            text: "DPI 우회 (GoodbyeDPI)"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Switch {
                            id: dpiSwitch
                            checked: SettingsModel.dpiBypass
                            onToggled: SettingsModel.dpiBypass = checked

                            indicator: Rectangle {
                                implicitWidth: 40
                                implicitHeight: 20
                                x: dpiSwitch.leftPadding
                                y: parent.height / 2 - height / 2
                                radius: 10
                                color: dpiSwitch.checked ? Theme.accentNeon : Theme.surfaceLight
                                border.color: dpiSwitch.checked ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1

                                Rectangle {
                                    x: dpiSwitch.checked ? parent.width - width - 2 : 2
                                    y: 2
                                    width: 16
                                    height: 16
                                    radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }
                    }

                    Text {
                        text: "크롤링 시 SNI 차단 우회 (tools/goodbyedpi 필요)"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        leftPadding: 168
                    }

                    Row {
                        layoutDirection: Qt.RightToLeft
                        width: parent.width
                        ActionButton {
                            text: "옵션 저장"
                            onClicked: SettingsModel.saveOptions()
                        }
                    }
                }
            }

            // ── 전역 번역 노트 ──────────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "전역 번역 노트 (공통 규칙)"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    Text {
                        text: "모든 작품 번역에 공통 적용되는 노트입니다. Gemini 프롬프트의 {{note}}에 작품/배우 노트와 함께 합쳐 주입됩니다.\n섹션 헤더 권장: [전역 규칙], [용어/은어 매핑], [고정 표기/호칭 사전]"
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textMuted
                        wrapMode: Text.Wrap
                        width: parent.width
                    }

                    Rectangle {
                        width: parent.width
                        height: 240
                        radius: Theme.radiusSm
                        color: Theme.surfaceLight
                        border.color: noteGlobalArea.activeFocus ? Theme.accentNeon : Theme.glassBorder
                        border.width: 1

                        AppScrollView {
                            anchors.fill: parent
                            anchors.margins: 4
                            clip: true

                            TextArea {
                                id: noteGlobalArea
                                width: parent.width
                                placeholderText: "[전역 규칙]\n- 출력은 100% 한국어 구어체. 번역투 금지.\n- 한 줄은 한 줄로: 문장 합치기 금지.\n\n[용어/은어 매핑]\n- 원어 => 번역어"
                                text: SettingsModel.translationNoteGlobal
                                onTextChanged: SettingsModel.translationNoteGlobal = text
                                wrapMode: TextArea.Wrap
                                selectByMouse: true
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontBody
                                background: null
                            }
                        }
                    }

                    Row {
                        layoutDirection: Qt.RightToLeft
                        width: parent.width
                        ActionButton {
                            text: "노트 저장"
                            onClicked: SettingsModel.saveOptions()
                        }
                    }
                }
            }

            // ── LADA 모자이크 제거 ──────────────────────
            GlassCard {
                width: parent.width
                autoSize: true

                Column {
                    width: parent.width
                    spacing: Theme.spacingSm

                    Text {
                        text: "LADA 모자이크 제거"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    // CUDA 디바이스 표시
                    Column {
                        width: parent.width
                        spacing: 4
                        Text {
                            text: "감지된 CUDA 디바이스"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                        }
                        Text {
                            text: (SettingsModel.cudaDevices && SettingsModel.cudaDevices.length > 0)
                                  ? SettingsModel.cudaDevices.join("\n")
                                  : "NVIDIA GPU 미감지 (nvidia-smi 없음)"
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textMuted
                            wrapMode: Text.Wrap
                        }
                    }

                    Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

                    // 병렬 처리 수 / PASS 수
                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "병렬 처리 수"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ComboBox {
                            id: ladaParallelCombo
                            model: ["1", "2", "3"]
                            width: 120
                            currentIndex: Math.max(0, Math.min(2, (SettingsModel.ladaParallel || 2) - 1))
                            onCurrentIndexChanged: {
                                var vals = [1,2,3];
                                SettingsModel.ladaParallel = vals[currentIndex] || 2;
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: ladaParallelCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }

                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "PASS 수"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ComboBox {
                            id: ladaPassesCombo
                            model: ["1", "2", "3"]
                            width: 120
                            currentIndex: Math.max(0, Math.min(2, (SettingsModel.ladaPasses || 2) - 1))
                            onCurrentIndexChanged: {
                                var vals = [1,2,3];
                                SettingsModel.ladaPasses = vals[currentIndex] || 2;
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: ladaPassesCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }

                    // 인코더 / 프리셋 / FP16
                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "인코더"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ComboBox {
                            id: ladaEncoderCombo
                            model: ["h264_nvenc", "hevc_amf", "hevc_nvenc"]
                            width: 220
                            currentIndex: {
                                var m = {"h264_nvenc":0,"hevc_amf":1,"hevc_nvenc":2};
                                return m[SettingsModel.ladaEncoder] !== undefined ? m[SettingsModel.ladaEncoder] : 2;
                            }
                            onCurrentIndexChanged: {
                                var vals = ["h264_nvenc","hevc_amf","hevc_nvenc"];
                                SettingsModel.ladaEncoder = vals[currentIndex] || "hevc_nvenc";
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: ladaEncoderCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }

                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "인코딩 프리셋"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        ComboBox {
                            id: ladaPresetCombo
                            model: ["h264-nvidia-gpu-fast", "hevc-nvidia-gpu-balanced", "hevc-nvidia-gpu-uhq"]
                            width: 260
                            currentIndex: {
                                var m = {"h264-nvidia-gpu-fast":0,"hevc-nvidia-gpu-balanced":1,"hevc-nvidia-gpu-uhq":2};
                                return m[SettingsModel.ladaEncodingPreset] !== undefined ? m[SettingsModel.ladaEncodingPreset] : 1;
                            }
                            onCurrentIndexChanged: {
                                var vals = ["h264-nvidia-gpu-fast","hevc-nvidia-gpu-balanced","hevc-nvidia-gpu-uhq"];
                                SettingsModel.ladaEncodingPreset = vals[currentIndex] || "hevc-nvidia-gpu-balanced";
                            }
                            background: Rectangle {
                                radius: Theme.radiusSm
                                color: Theme.surfaceLight
                                border.color: Theme.glassBorder
                                border.width: 1
                            }
                            contentItem: Text {
                                text: ladaPresetCombo.displayText
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                leftPadding: Theme.spacingSm
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.Wrap
                        font.pixelSize: Theme.fontCaption - 1
                        color: Theme.textMuted
                        text: "UHQ(최고)는 비트레이트가 높아 용량이 클 수 있습니다. 용량을 줄이려면 balanced 또는 fast를 선택하세요. (이전에는 NVENC 인코더가 lada 인코딩 프리셋을 무시해 출력이 비정상적으로 커질 수 있었는데, 이제는 프리셋이 적용됩니다.)"
                    }

                    Row {
                        spacing: Theme.spacingSm
                        width: parent.width
                        Text {
                            text: "FP16 정밀도 사용"
                            font.pixelSize: Theme.fontBody
                            color: Theme.textSecondary
                            width: 160
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Switch {
                            id: ladaFp16Switch
                            checked: SettingsModel.ladaFp16
                            onToggled: SettingsModel.ladaFp16 = checked

                            indicator: Rectangle {
                                implicitWidth: 40
                                implicitHeight: 20
                                x: ladaFp16Switch.leftPadding
                                y: parent.height / 2 - height / 2
                                radius: 10
                                color: ladaFp16Switch.checked ? Theme.accentNeon : Theme.surfaceLight
                                border.color: ladaFp16Switch.checked ? Theme.accentNeon : Theme.glassBorder
                                border.width: 1

                                Rectangle {
                                    x: ladaFp16Switch.checked ? parent.width - width - 2 : 2
                                    y: 2
                                    width: 16
                                    height: 16
                                    radius: 8
                                    color: "white"
                                    Behavior on x { NumberAnimation { duration: 150 } }
                                }
                            }
                        }
                    }

                    // PASS 별 옵션
                    Column {
                        width: parent.width
                        spacing: Theme.spacingSm

                        // PASS 1
                        GlassCard {
                            width: parent.width
                            visible: true
                            autoSize: true
                            Column {
                                width: parent.width
                                spacing: Theme.spacingSm
                                Text { text: "PASS 1"; color: Theme.textPrimary; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "모자이크 탐지 모델"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    ComboBox {
                                        id: pass1Det
                                        model: ["v2", "v4-fast", "v4-accurate"]
                                        width: 200
                                        currentIndex: { var m={"v2":0,"v4-fast":1,"v4-accurate":2}; return m[SettingsModel.ladaPass1DetModel] !== undefined ? m[SettingsModel.ladaPass1DetModel] : 1; }
                                        onCurrentIndexChanged: { var v=["v2","v4-fast","v4-accurate"]; SettingsModel.ladaPass1DetModel = v[currentIndex] || "v4-fast"; }
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "모자이크 제거 모델"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    ComboBox {
                                        id: pass1Rest
                                        model: ["basicvsrpp-v1.2", "deepmosaics"]
                                        width: 220
                                        currentIndex: { var m={"basicvsrpp-v1.2":0,"deepmosaics":1}; return m[SettingsModel.ladaPass1RestModel] !== undefined ? m[SettingsModel.ladaPass1RestModel] : 0; }
                                        onCurrentIndexChanged: { var v=["basicvsrpp-v1.2","deepmosaics"]; SettingsModel.ladaPass1RestModel = v[currentIndex] || "basicvsrpp-v1.2"; }
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "최대 클립 길이"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    Slider {
                                        id: pass1ClipSlider
                                        from: 20; to: 400; stepSize: 1
                                        width: parent.width - 160 - 90 - Theme.spacingSm * 2
                                        value: SettingsModel.ladaPass1MaxClipLength
                                        onMoved: SettingsModel.ladaPass1MaxClipLength = Math.round(value)
                                    }
                                    TextField {
                                        id: pass1ClipField
                                        width: 80
                                        text: "" + (SettingsModel.ladaPass1MaxClipLength || 180)
                                        inputMethodHints: Qt.ImhDigitsOnly
                                        onEditingFinished: SettingsModel.ladaPass1MaxClipLength = parseInt(text) || 180
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "얼굴모자이크 제거"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    Switch { checked: SettingsModel.ladaPass1DetectFace; onToggled: SettingsModel.ladaPass1DetectFace = checked }
                                }
                            }
                        }

                        // PASS 2
                        GlassCard {
                            width: parent.width
                            visible: (SettingsModel.ladaPasses || 1) >= 2
                            autoSize: true
                            Column {
                                width: parent.width
                                spacing: Theme.spacingSm
                                Text { text: "PASS 2"; color: Theme.textPrimary; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "모자이크 탐지 모델"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    ComboBox {
                                        id: pass2Det
                                        model: ["v2", "v4-fast", "v4-accurate"]
                                        width: 200
                                        currentIndex: { var m={"v2":0,"v4-fast":1,"v4-accurate":2}; return m[SettingsModel.ladaPass2DetModel] !== undefined ? m[SettingsModel.ladaPass2DetModel] : 1; }
                                        onCurrentIndexChanged: { var v=["v2","v4-fast","v4-accurate"]; SettingsModel.ladaPass2DetModel = v[currentIndex] || "v4-fast"; }
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "모자이크 제거 모델"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    ComboBox {
                                        id: pass2Rest
                                        model: ["basicvsrpp-v1.2", "deepmosaics"]
                                        width: 220
                                        currentIndex: { var m={"basicvsrpp-v1.2":0,"deepmosaics":1}; return m[SettingsModel.ladaPass2RestModel] !== undefined ? m[SettingsModel.ladaPass2RestModel] : 0; }
                                        onCurrentIndexChanged: { var v=["basicvsrpp-v1.2","deepmosaics"]; SettingsModel.ladaPass2RestModel = v[currentIndex] || "basicvsrpp-v1.2"; }
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "최대 클립 길이"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    Slider {
                                        id: pass2ClipSlider
                                        from: 20; to: 400; stepSize: 1
                                        width: parent.width - 160 - 90 - Theme.spacingSm * 2
                                        value: SettingsModel.ladaPass2MaxClipLength
                                        onMoved: SettingsModel.ladaPass2MaxClipLength = Math.round(value)
                                    }
                                    TextField {
                                        id: pass2ClipField
                                        width: 80
                                        text: "" + (SettingsModel.ladaPass2MaxClipLength || 180)
                                        inputMethodHints: Qt.ImhDigitsOnly
                                        onEditingFinished: SettingsModel.ladaPass2MaxClipLength = parseInt(text) || 180
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "얼굴모자이크 제거"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    Switch { checked: SettingsModel.ladaPass2DetectFace; onToggled: SettingsModel.ladaPass2DetectFace = checked }
                                }
                            }
                        }

                        // PASS 3
                        GlassCard {
                            width: parent.width
                            visible: (SettingsModel.ladaPasses || 1) >= 3
                            autoSize: true
                            Column {
                                width: parent.width
                                spacing: Theme.spacingSm
                                Text { text: "PASS 3"; color: Theme.textPrimary; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "모자이크 탐지 모델"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    ComboBox {
                                        id: pass3Det
                                        model: ["v2", "v4-fast", "v4-accurate"]
                                        width: 200
                                        currentIndex: { var m={"v2":0,"v4-fast":1,"v4-accurate":2}; return m[SettingsModel.ladaPass3DetModel] !== undefined ? m[SettingsModel.ladaPass3DetModel] : 1; }
                                        onCurrentIndexChanged: { var v=["v2","v4-fast","v4-accurate"]; SettingsModel.ladaPass3DetModel = v[currentIndex] || "v4-fast"; }
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "모자이크 제거 모델"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    ComboBox {
                                        id: pass3Rest
                                        model: ["basicvsrpp-v1.2", "deepmosaics"]
                                        width: 220
                                        currentIndex: { var m={"basicvsrpp-v1.2":0,"deepmosaics":1}; return m[SettingsModel.ladaPass3RestModel] !== undefined ? m[SettingsModel.ladaPass3RestModel] : 0; }
                                        onCurrentIndexChanged: { var v=["basicvsrpp-v1.2","deepmosaics"]; SettingsModel.ladaPass3RestModel = v[currentIndex] || "basicvsrpp-v1.2"; }
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "최대 클립 길이"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    Slider {
                                        id: pass3ClipSlider
                                        from: 20; to: 400; stepSize: 1
                                        width: parent.width - 160 - 90 - Theme.spacingSm * 2
                                        value: SettingsModel.ladaPass3MaxClipLength
                                        onMoved: SettingsModel.ladaPass3MaxClipLength = Math.round(value)
                                    }
                                    TextField {
                                        id: pass3ClipField
                                        width: 80
                                        text: "" + (SettingsModel.ladaPass3MaxClipLength || 180)
                                        inputMethodHints: Qt.ImhDigitsOnly
                                        onEditingFinished: SettingsModel.ladaPass3MaxClipLength = parseInt(text) || 180
                                    }
                                }
                                Row {
                                    spacing: Theme.spacingSm; width: parent.width
                                    Text { text: "얼굴모자이크 제거"; width: 160; color: Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                                    Switch { checked: SettingsModel.ladaPass3DetectFace; onToggled: SettingsModel.ladaPass3DetectFace = checked }
                                }
                            }
                        }
                    }

                    Row {
                        layoutDirection: Qt.RightToLeft
                        width: parent.width
                        ActionButton {
                            text: "LADA 옵션 저장"
                            onClicked: SettingsModel.saveOptions()
                        }
                    }
                }
            }

            GlassCard {
                width: parent.width
                autoSize: true
                Column {
                    width: parent.width
                    spacing: Theme.spacingSm
                    Text {
                        text: "파이프라인 · 문제 해결"
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "자막 LLM 실패(OpenRouter 티어·검열)는 docs/llm_troubleshooting.md 를 참고하세요. " +
                              "부트 크래시(logs/crash_report.txt)와 별도로, Harvest/STT/자막 실패 기록은 data/error/04_ERROR/ 에 저장됩니다."
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textSecondary
                    }
                    Row {
                        width: parent.width
                        layoutDirection: Qt.RightToLeft
                        ActionButton {
                            text: "실패 작업 폴더 열기 (04_ERROR)"
                            onClicked: SettingsModel.openPipelineErrorFolder()
                        }
                    }
                }
            }

            // ── 버전 정보 ───────────────────────────────
            Text {
                text: "JAVSTORY Pro v3.0 — PySide6 + QML"
                font.pixelSize: Theme.fontCaption
                color: Theme.textMuted
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Item { height: Theme.spacingLg }
        }
    }
}