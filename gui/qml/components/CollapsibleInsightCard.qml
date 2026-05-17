import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root
    autoSize: false
    Layout.fillWidth: true
    Layout.bottomMargin: Theme.spacingLg
    clip: false

    property string title: ""
    property string subtitle: ""
    property string icon: ""
    property bool expanded: true
    /** 접힘 시 고정 높이(0이면 headerRowHeight + 여백) */
    property int collapsedHeight: 0
    property int expandedHeight: 200
    /** 헤더 1줄 기준 고정 — implicitHeight↔preferredHeight 루프 방지 */
    property int headerRowHeight: 40

    readonly property int cardMargins: Theme.spacingMd
    readonly property int collapsedBodyHeight: root.collapsedHeight > 0
        ? root.collapsedHeight
        : root.headerRowHeight + root.cardMargins * 2

    default property alias content: bodyColumn.data

    Layout.preferredHeight: root.expanded ? root.expandedHeight : root.collapsedBodyHeight

    ColumnLayout {
        width: parent.width
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: root.cardMargins
        spacing: Theme.spacingSm

        Item {
            id: headerBar
            Layout.fillWidth: true
            height: root.headerRowHeight

            RowLayout {
                id: headerRow
                anchors.fill: parent
                spacing: Theme.spacingSm

                InsightSectionHeader {
                    Layout.fillWidth: true
                    icon: root.icon
                    title: root.title
                    subtitle: root.subtitle
                }

                Text {
                    text: root.expanded ? "▲" : "▼"
                    font.pixelSize: 10
                    color: Theme.textMuted
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 14
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.expanded = !root.expanded
            }
        }

        ColumnLayout {
            id: bodyColumn
            Layout.fillWidth: true
            visible: root.expanded
            spacing: Theme.spacingSm
        }
    }
}
