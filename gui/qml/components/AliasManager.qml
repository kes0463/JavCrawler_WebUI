import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root

    property var aliases: []  // [{alias_name, alias_type, is_primary}]
    property int actressId: 0
    signal addAlias(string name, string type, bool isPrimary)
    signal removeAlias(int aliasId)

    title: "별명 관리 (" + (aliases.length || 0) + ")"

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacingMd

        // Add form
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.spacingSm

            TextField {
                id: aliasInput
                Layout.fillWidth: true
                placeholderText: "별명 입력 (예: みやむら れい)"
                onAccepted: addButton.clicked()
            }

            ComboBox {
                id: typeCombo
                model: ["stage", "old", "korean", "english", "other"]
                currentIndex: 0
                implicitWidth: 110
            }

            CheckBox {
                id: primaryCheck
                text: "Primary"
                checked: false
            }

            ActionButton {
                id: addButton
                text: "추가"
                onClicked: {
                    var name = aliasInput.text.trim()
                    if (name) {
                        root.addAlias(name, typeCombo.currentText, primaryCheck.checked)
                        aliasInput.text = ""
                        primaryCheck.checked = false
                    }
                }
            }
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            Column {
                width: parent.width
                spacing: 6

                Repeater {
                    model: root.aliases || []

                    delegate: GlassCard {
                        width: parent.width
                        height: 42
                        contentMargins: 12

                        RowLayout {
                            anchors.fill: parent
                            spacing: Theme.spacingMd

                            Text {
                                text: modelData.alias_name
                                color: modelData.is_primary ? Theme.accentNeon : Theme.textPrimary
                                font.bold: modelData.is_primary
                                Layout.fillWidth: true
                            }

                            Text {
                                text: modelData.alias_type || "stage"
                                color: Theme.textMuted
                                font.pixelSize: 12
                            }

                            ActionButton {
                                text: "×"
                                danger: true
                                onClicked: root.removeAlias(modelData.alias_id || 0)
                            }
                        }
                    }
                }

                Text {
                    visible: (root.aliases || []).length === 0
                    text: "등록된 별명이 없습니다.\n검색 정확도 향상을 위해 별명을 추가하세요."
                    color: Theme.textMuted
                    horizontalAlignment: Text.AlignHCenter
                    anchors.horizontalCenter: parent.horizontalCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
