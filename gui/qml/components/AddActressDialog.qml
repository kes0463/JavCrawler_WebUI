import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Dialog {
    id: root

    property var actressModel: null
    signal actressAdded(int newId)

    title: "새 배우 추가"
    modal: true
    width: 640
    height: 700

    background: Rectangle {
        color: Theme.bgPrimary
        border.color: Theme.glassBorder
        border.width: 1
        radius: Theme.radiusMd
    }

    header: Item {
        implicitHeight: 52
        RowLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            Text {
                text: root.title
                font.pixelSize: Theme.fontSubtitle
                font.bold: true
                color: Theme.textPrimary
                Layout.fillWidth: true
            }
            ActionButton {
                text: "×"
                onClicked: root.close()
            }
        }
    }

    // ── 폼 데이터 ──────────────────────────────────
    property alias nameJa:    fieldNameJa.text
    property alias nameKo:    fieldNameKo.text
    property alias nameEn:    fieldNameEn.text
    property alias genres:    fieldGenres.text
    property alias agency:    fieldAgency.text
    property alias cupSize:   fieldCupSize.text
    property alias memo:      fieldMemo.text
    property alias profileText: fieldProfileText.text

    function _intVal(t) { return parseInt(t) || 0 }
    function _floatVal(t) { return parseFloat(t) || 0.0 }

    function normalizeCupSize(raw) {
        if (raw === undefined || raw === null) return ""
        var s = String(raw).trim()
        if (!s) return ""
        s = s.replace(/cup/gi, "").replace(/컵/g, "").trim()
        if (!s) return ""
        var ch = s.charAt(0)
        if (ch >= "a" && ch <= "z") return ch.toUpperCase()
        if (ch >= "A" && ch <= "Z") return ch
        return ""
    }

    function formatCupSize(raw) {
        var letter = normalizeCupSize(raw)
        return letter ? (letter + "컵") : "-"
    }

    function _buildData() {
        return {
            name_ja:        fieldNameJa.text.trim(),
            name_ko:        fieldNameKo.text.trim(),
            name_en:        fieldNameEn.text.trim(),
            genres:         fieldGenres.text.trim(),
            agency:         fieldAgency.text.trim(),
            cup_size:       root.normalizeCupSize(fieldCupSize.text) || null,
            profile_text:   fieldProfileText.text.trim(),
            memo:           fieldMemo.text.trim(),
            height:         _intVal(fieldHeight.text),
            bust:           _intVal(fieldBust.text),
            waist:          _intVal(fieldWaist.text),
            hip:            _intVal(fieldHip.text),
            birth_date:     fieldBirthDate.text.trim() || null,
            debut_date:     fieldDebutDate.text.trim() || null,
            user_score:     _floatVal(fieldUserScore.text),
            favorite_intensity: 5.0,
            is_favorite:    false,
        }
    }

    function _reset() {
        fieldNameJa.text = ""
        fieldNameKo.text = ""
        fieldNameEn.text = ""
        fieldGenres.text = ""
        fieldAgency.text = ""
        fieldCupSize.text = ""
        fieldHeight.text = ""
        fieldBust.text = ""
        fieldWaist.text = ""
        fieldHip.text = ""
        fieldBirthDate.text = ""
        fieldDebutDate.text = ""
        fieldUserScore.text = "0"
        fieldProfileText.text = ""
        fieldMemo.text = ""
    }

    onOpened: _reset()

    contentItem: ScrollView {
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: parent.width
            spacing: Theme.spacingMd

            // ── 이름 ─────────────────────────────────
            GlassCard {
                Layout.fillWidth: true
                autoSize: true
                title: "이름 *"

                GridLayout {
                    columns: 3
                    columnSpacing: Theme.spacingMd
                    rowSpacing: Theme.spacingSm
                    width: parent.width

                    Text { text: "일본어 (JA)"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "한국어 (KO) *"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "영어 (EN)"; color: Theme.textSecondary; font.pixelSize: 12 }

                    TextField {
                        id: fieldNameJa
                        Layout.fillWidth: true
                        placeholderText: "예: 三上悠亜"
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                    TextField {
                        id: fieldNameKo
                        Layout.fillWidth: true
                        placeholderText: "예: 미카미 유아 *"
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.accentNeon; border.width: 1 }
                    }
                    TextField {
                        id: fieldNameEn
                        Layout.fillWidth: true
                        placeholderText: "예: Yua Mikami"
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                }
            }

            // ── 신체 정보 ────────────────────────────
            GlassCard {
                Layout.fillWidth: true
                autoSize: true
                title: "신체 정보"

                GridLayout {
                    columns: 4
                    columnSpacing: Theme.spacingMd
                    rowSpacing: Theme.spacingSm
                    width: parent.width

                    Text { text: "키 (cm)"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "바스트"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "허리"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "힙"; color: Theme.textSecondary; font.pixelSize: 12 }

                    TextField {
                        id: fieldHeight
                        Layout.fillWidth: true
                        placeholderText: "165"
                        inputMethodHints: Qt.ImhDigitsOnly
                        validator: IntValidator { bottom: 0; top: 250 }
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                    TextField {
                        id: fieldBust
                        Layout.fillWidth: true
                        placeholderText: "85"
                        inputMethodHints: Qt.ImhDigitsOnly
                        validator: IntValidator { bottom: 0; top: 200 }
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                    TextField {
                        id: fieldWaist
                        Layout.fillWidth: true
                        placeholderText: "58"
                        inputMethodHints: Qt.ImhDigitsOnly
                        validator: IntValidator { bottom: 0; top: 200 }
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                    TextField {
                        id: fieldHip
                        Layout.fillWidth: true
                        placeholderText: "86"
                        inputMethodHints: Qt.ImhDigitsOnly
                        validator: IntValidator { bottom: 0; top: 200 }
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }

                    Text { text: "컵사이즈"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "생년월일"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "데뷔일"; color: Theme.textSecondary; font.pixelSize: 12 }
                    Text { text: "시청 점수"; color: Theme.textSecondary; font.pixelSize: 12 }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        TextField {
                            id: fieldCupSize
                            Layout.preferredWidth: 56
                            maximumLength: 1
                            placeholderText: "E"
                            color: Theme.textPrimary
                            inputMethodHints: Qt.ImhUppercaseOnly
                            background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                            onTextChanged: {
                                var n = root.normalizeCupSize(text)
                                if (text !== n) {
                                    var pos = cursorPosition
                                    text = n
                                    cursorPosition = Math.min(pos, text.length)
                                }
                            }
                        }

                        Text {
                            visible: root.formatCupSize(fieldCupSize.text) !== "-"
                            text: root.formatCupSize(fieldCupSize.text)
                            color: Theme.textSecondary
                            font.pixelSize: 13
                            font.weight: Font.Medium
                        }
                    }
                    TextField {
                        id: fieldBirthDate
                        Layout.fillWidth: true
                        placeholderText: "1996-04-16"
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                    TextField {
                        id: fieldDebutDate
                        Layout.fillWidth: true
                        placeholderText: "2015-01-01"
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                    TextField {
                        id: fieldUserScore
                        Layout.fillWidth: true
                        text: "0"
                        placeholderText: "0.0"
                        inputMethodHints: Qt.ImhFormattedNumbersOnly
                        validator: DoubleValidator { bottom: 0; top: 10; decimals: 1 }
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                    }
                }
            }

            // ── 소속 / 장르 ──────────────────────────
            GlassCard {
                Layout.fillWidth: true
                autoSize: true
                title: "소속 / 장르"

                ColumnLayout {
                    width: parent.width
                    spacing: Theme.spacingSm

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingMd
                        Text { text: "소속사"; color: Theme.textSecondary; font.pixelSize: 12; Layout.preferredWidth: 60 }
                        TextField {
                            id: fieldAgency
                            Layout.fillWidth: true
                            placeholderText: "예: Idea Pocket"
                            color: Theme.textPrimary
                            background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.spacingMd
                        Text { text: "장르"; color: Theme.textSecondary; font.pixelSize: 12; Layout.preferredWidth: 60 }
                        TextField {
                            id: fieldGenres
                            Layout.fillWidth: true
                            placeholderText: "NTR,조교,아줌마  (쉼표 구분)"
                            color: Theme.textPrimary
                            background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                        }
                    }
                }
            }

            // ── 프로필 소개 ──────────────────────────
            GlassCard {
                Layout.fillWidth: true
                autoSize: true
                title: "프로필 소개"

                TextArea {
                    id: fieldProfileText
                    width: parent.width
                    height: 80
                    placeholderText: "AVDBS 등에서 가져온 소개 문구"
                    wrapMode: TextEdit.Wrap
                    color: Theme.textPrimary
                    background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                }
            }

            // ── 메모 ─────────────────────────────────
            GlassCard {
                Layout.fillWidth: true
                autoSize: true
                title: "개인 메모"

                TextArea {
                    id: fieldMemo
                    width: parent.width
                    height: 80
                    placeholderText: "개인 취향 메모 (중요)..."
                    wrapMode: TextEdit.Wrap
                    color: Theme.textPrimary
                    background: Rectangle { color: Theme.surfaceLight; radius: 6; border.color: Theme.glassBorder }
                }
            }

            // ── 필수 입력 안내 ───────────────────────
            Text {
                Layout.fillWidth: true
                text: "* 한국어 이름은 필수 입력입니다. 폴더명 생성에 사용됩니다."
                color: Theme.textMuted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
            }
        }
    }

    footer: RowLayout {
        spacing: Theme.spacingMd
        anchors.margins: Theme.spacingMd

        Item { Layout.fillWidth: true }

        ActionButton {
            text: "취소"
            onClicked: root.close()
        }

        ActionButton {
            text: "저장"
            primary: true
            onClicked: {
                var nameKo = fieldNameKo.text.trim()
                if (!nameKo) {
                    fieldNameKo.background.border.color = "red"
                    return
                }
                if (root.actressModel) {
                    var newId = root.actressModel.addActress(root._buildData())
                    if (newId > 0) {
                        root.actressAdded(newId)
                        root.close()
                    }
                }
            }
        }
    }
}
