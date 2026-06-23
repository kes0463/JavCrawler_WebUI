import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root

    property int actressId: 0
    property string nameKo: ""
    property string nameJa: ""
    property string profileImage: ""
    property real userScore: 0.0
    property int workCount: 0
    property bool showWorkCount: false
    property bool isFavorite: false
    property string genres: ""
    property bool selected: false

    signal clicked(int actressId)

    implicitWidth: 220
    implicitHeight: 320
    hoverGlow: true
    contentMargins: Theme.spacingSm
    clip: true

    border.color: root.selected
        ? Theme.accentNeon
        : (root.hovered && hoverGlow ? Theme.glassBorderHover : Theme.glassBorder)
    border.width: root.selected ? 2 : 1

    readonly property var _genreTags: {
        var tags = []
        var parts = (root.genres || "").split(",")
        for (var i = 0; i < parts.length; i++) {
            var g = parts[i].trim()
            if (g.length > 0)
                tags.push(g)
            if (tags.length >= 2)
                break
        }
        return tags
    }
    readonly property bool _showMetaRow: root.showWorkCount
        || root.userScore > 0
        || _genreTags.length > 0

    Column {
        anchors.fill: parent
        spacing: Theme.spacingXs

        Rectangle {
            id: photoFrame
            width: parent.width
            height: Math.max(140, Math.min(
                Math.round(width * 1.15),
                Math.round((root.height - root.contentMargins * 2) * 0.56)
            ))
            radius: Theme.radiusSm
            color: Theme.bgSecondary
            clip: true

            Image {
                anchors.fill: parent
                source: root.profileImage ? Theme.pathToUrl(root.profileImage) : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                sourceSize.width: Math.min(480, Math.round(photoFrame.width * 2))

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 40
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.65) }
                    }
                }
            }

            Rectangle {
                visible: root.isFavorite
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: 6
                width: 24
                height: 24
                radius: 12
                color: Theme.accentNeon

                Text {
                    anchors.centerIn: parent
                    text: "♥"
                    color: "white"
                    font.pixelSize: 14
                }
            }
        }

        Column {
            width: parent.width
            spacing: 2

            Text {
                width: parent.width
                text: root.nameKo || "이름 없음"
                color: Theme.textPrimary
                font.pixelSize: 15
                font.bold: true
                elide: Text.ElideRight
                maximumLineCount: 1
            }

            Text {
                width: parent.width
                visible: root.nameJa.length > 0
                text: root.nameJa
                color: Theme.textSecondary
                font.pixelSize: 12
                elide: Text.ElideRight
                maximumLineCount: 1
            }
        }

        RowLayout {
            width: parent.width
            visible: root._showMetaRow
            spacing: Theme.spacingXs

            Rectangle {
                visible: root.showWorkCount
                Layout.preferredHeight: 20
                width: worksCountText.width + 12
                radius: 10
                color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.15)
                border.color: Theme.accentNeon

                Text {
                    id: worksCountText
                    anchors.centerIn: parent
                    text: root.workCount + "작품"
                    color: Theme.accentNeon
                    font.pixelSize: 11
                    font.bold: true
                }
            }

            RatingWidget {
                visible: root.userScore > 0
                interactive: false
                starSize: 16
                rating: Math.round((root.userScore || 0) / 2)
            }

            Text {
                visible: root.userScore > 0
                text: root.userScore.toFixed(1)
                color: Theme.accentNeon
                font.pixelSize: 13
                font.bold: true
            }

            Item { Layout.fillWidth: true }

            Flow {
                visible: root._genreTags.length > 0
                spacing: 4
                Repeater {
                    model: root._genreTags
                    delegate: Rectangle {
                        width: chipText.width + 12
                        height: 20
                        radius: 10
                        color: Theme.surfaceLight
                        border.color: Theme.glassBorder

                        Text {
                            id: chipText
                            anchors.centerIn: parent
                            text: modelData
                            color: Theme.textMuted
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        onClicked: root.clicked(root.actressId)
        cursorShape: Qt.PointingHandCursor
    }
}
