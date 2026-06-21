import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Item {
    id: root

    property string actressNameKo: ""
    property string profileImageUrl: ""
    property var galleryImages: []

    signal addProfileImageRequested()
    signal addGalleryImageRequested()
    signal profileImagesDropped(var urls)
    signal galleryImagesDropped(var urls)

    property string previewOverlayUrl: ""

    readonly property int galleryColumns: 3
    readonly property int gallerySpacing: 8
    readonly property int galleryAreaWidth: galleryArea.width > 0
        ? galleryArea.width
        : Math.max(360, root.width * 0.55)
    readonly property int galleryThumbSize: Math.min(
        150,
        Math.max(96, Math.floor((galleryAreaWidth - gallerySpacing * (galleryColumns - 1)) / galleryColumns * 0.75))
    )
    readonly property int galleryRows: {
        var n = (galleryImages || []).length
        return n > 0 ? Math.ceil(n / galleryColumns) : 1
    }
    readonly property int galleryGridHeight: galleryRows * galleryThumbSize + Math.max(0, galleryRows - 1) * gallerySpacing

    implicitWidth: 720
    implicitHeight: Math.max(300, galleryGridHeight + 72)

    Rectangle {
        anchors.fill: parent
        color: Theme.surface
        border.color: Theme.glassBorder
        border.width: 1
        radius: Theme.radiusMd
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.spacingMd
        spacing: Theme.spacingLg

        // ── 좌: 대표 사진 (profile/) ─────────────────
        ColumnLayout {
            Layout.preferredWidth: Math.max(200, parent.width * 0.30)
            Layout.fillHeight: true
            spacing: Theme.spacingSm

            Rectangle {
                id: profileFrame
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: Theme.radiusMd
                color: Theme.bgSecondary
                clip: true
                border.color: root.previewOverlayUrl === root.profileImageUrl && root.profileImageUrl
                    ? Theme.accentNeon
                    : (root.profileImageUrl ? Theme.accentNeon : Theme.glassBorder)
                border.width: root.previewOverlayUrl === root.profileImageUrl ? 2 : (root.profileImageUrl ? 1 : 0)

                Image {
                    anchors.fill: parent
                    anchors.margins: 2
                    source: root.profileImageUrl ? Theme.pathToUrl(root.profileImageUrl) : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: root.profileImageUrl !== ""
                }

                Column {
                    anchors.centerIn: parent
                    spacing: Theme.spacingSm
                    visible: root.profileImageUrl === ""
                    opacity: 0.55

                    Text {
                        text: "📷"
                        font.pixelSize: 40
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                    Text {
                        text: "대표 사진 없음\n(클릭 또는 드래그)"
                        color: Theme.textSecondary
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        anchors.horizontalCenter: parent.horizontalCenter
                    }
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 32
                    visible: root.profileImageUrl !== ""
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.65) }
                    }
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        text: root.previewOverlayUrl === root.profileImageUrl
                            ? "크게 보기 (닫기)"
                            : "대표 사진 · 클릭 → 크게 보기"
                        color: "white"
                        font.pixelSize: 11
                        font.bold: true
                    }
                }

                MouseArea {
                    id: profileMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (root.profileImageUrl) {
                            if (root.previewOverlayUrl === root.profileImageUrl)
                                root.previewOverlayUrl = ""
                            else
                                root.previewOverlayUrl = root.profileImageUrl
                        } else {
                            root.addProfileImageRequested()
                        }
                    }
                }

                DropArea {
                    anchors.fill: parent
                    onEntered: function(drag) {
                        if (drag.hasUrls) drag.accept(Qt.CopyAction)
                    }
                    onDropped: function(drop) {
                        if (!drop.hasUrls) return
                        var urls = []
                        for (var i = 0; i < drop.urls.length; i++)
                            urls.push(drop.urls[i].toString())
                        root.profileImagesDropped(urls)
                    }
                }
            }

            ActionButton {
                Layout.fillWidth: true
                text: root.profileImageUrl ? "대표 사진 변경" : "대표 사진 추가"
                iconSource: "📷"
                primary: false
                onClicked: root.addProfileImageRequested()
            }
        }

        // ── 우: 갤러리 (gallery/) ───────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.spacingSm

            RowLayout {
                Layout.fillWidth: true

                Text {
                    text: "▶  " + (root.actressNameKo || "배우") + "의 다른 사진"
                    color: Theme.accentNeon
                    font.pixelSize: 14
                    font.bold: true
                    Layout.fillWidth: true
                }

                ActionButton {
                    text: "갤러리 추가"
                    iconSource: "📷"
                    onClicked: root.addGalleryImageRequested()
                }
            }

            Text {
                text: "썸네일 클릭 → 크게 보기 (바깥 클릭 시 닫기)"
                color: Theme.textMuted
                font.pixelSize: 11
                visible: (root.galleryImages || []).length > 0
            }

            Item {
                id: galleryArea
                Layout.fillWidth: true
                Layout.preferredHeight: root.galleryGridHeight

                Grid {
                    width: parent.width
                    columns: root.galleryColumns
                    rowSpacing: root.gallerySpacing
                    columnSpacing: root.gallerySpacing

                    Repeater {
                        model: root.galleryImages || []

                        delegate: Rectangle {
                            width: root.galleryThumbSize
                            height: root.galleryThumbSize
                            radius: Theme.radiusSm
                            color: Theme.bgSecondary
                            border.color: root.previewOverlayUrl === (modelData.image_url || "")
                                ? Theme.accentNeon
                                : (thumbMa.containsMouse ? Theme.glassBorderHover : Theme.glassBorder)
                            border.width: root.previewOverlayUrl === (modelData.image_url || "") ? 2 : 1

                            Image {
                                anchors.fill: parent
                                anchors.margins: 2
                                source: modelData.image_url ? Theme.pathToUrl(modelData.image_url) : ""
                                fillMode: Image.PreserveAspectFit
                                asynchronous: true
                            }

                            MouseArea {
                                id: thumbMa
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (!modelData.image_url) return
                                    if (root.previewOverlayUrl === modelData.image_url)
                                        root.previewOverlayUrl = ""
                                    else
                                        root.previewOverlayUrl = modelData.image_url
                                }
                            }
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    visible: (root.galleryImages || []).length === 0
                    text: "갤러리 사진 없음\n(드래그 또는 「갤러리 추가」)"
                    color: Theme.textMuted
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                }

                DropArea {
                    anchors.fill: parent
                    onEntered: function(drag) {
                        if (drag.hasUrls) drag.accept(Qt.CopyAction)
                    }
                    onDropped: function(drop) {
                        if (!drop.hasUrls) return
                        var urls = []
                        for (var i = 0; i < drop.urls.length; i++)
                            urls.push(drop.urls[i].toString())
                        root.galleryImagesDropped(urls)
                    }
                }
            }
        }
    }
}
