import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"
import "../.."

ColumnLayout {
    id: tab
    width: parent ? parent.width : 0
    spacing: Theme.spacingLg

    property var libraryDist: ({ actors: [], genres: [], makers: [] })
    property var actors: []
    property var genres: []
    property var makers: []
    property var actorCollections: ({ actors: [] })
    property var pipeline: ({})

    function genreColor(idx) {
        var palette = [
            "#00E5FF", "#FF4081", "#FFD700", "#7C4DFF",
            "#00E676", "#FF9F43", "#48DBFB", "#FF6B6B",
        ]
        return palette[idx % palette.length]
    }

    GlassCard {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        Layout.maximumWidth: 1200
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredHeight: 450
        autoSize: false

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingMd

            InsightSectionHeader {
                Layout.fillWidth: true
                icon: "📦"
                title: "라이브러리 수집 현황"
                subtitle: "보유 중인 전체 작품 수 기준"
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 40

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    spacing: Theme.spacingMd
                    Text { text: "최다 보유 배우"; font.pixelSize: 15; color: Theme.textSecondary; font.weight: Font.DemiBold }
                    AppScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        contentWidth: availableWidth
                        Column {
                            width: parent.width; spacing: 2
                            Repeater {
                                model: tab.libraryDist.actors || []
                                Rectangle {
                                    width: parent.width
                                    height: distActorInner.implicitHeight + 8
                                    radius: 4
                                    color: distActorMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"
                                    RowLayout {
                                        id: distActorInner
                                        anchors { left: parent.left; right: parent.right; leftMargin: 4; rightMargin: 4; verticalCenter: parent.verticalCenter }
                                        spacing: 8
                                        Text {
                                            text: modelData.name
                                            font.pixelSize: 14
                                            color: distActorMa.containsMouse ? Theme.accentNeon : Theme.textPrimary
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: modelData.count + "편"
                                            font.pixelSize: 13
                                            color: Theme.accentNeon
                                            font.weight: Font.Bold
                                            Layout.preferredWidth: 60
                                            horizontalAlignment: Text.AlignRight
                                        }
                                    }
                                    MouseArea {
                                        id: distActorMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: window.navigateToLibrarySearch(modelData.name)
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle { width: 1; Layout.fillHeight: true; color: Theme.glassBorder; Layout.topMargin: 20; Layout.bottomMargin: 20 }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    spacing: Theme.spacingMd
                    Text { text: "최다 보유 장르"; font.pixelSize: 15; color: Theme.textSecondary; font.weight: Font.DemiBold }
                    AppScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        contentWidth: availableWidth
                        Column {
                            width: parent.width; spacing: 2
                            Repeater {
                                model: tab.libraryDist.genres || []
                                Rectangle {
                                    width: parent.width
                                    height: distGenreInner.implicitHeight + 8
                                    radius: 4
                                    color: distGenreMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"
                                    RowLayout {
                                        id: distGenreInner
                                        anchors { left: parent.left; right: parent.right; leftMargin: 4; rightMargin: 4; verticalCenter: parent.verticalCenter }
                                        spacing: 8
                                        Text {
                                            text: modelData.name
                                            font.pixelSize: 14
                                            color: distGenreMa.containsMouse ? "#FF9F43" : Theme.textPrimary
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: modelData.count + "편"
                                            font.pixelSize: 13
                                            color: "#FF9F43"
                                            font.weight: Font.Bold
                                            Layout.preferredWidth: 60
                                            horizontalAlignment: Text.AlignRight
                                        }
                                    }
                                    MouseArea {
                                        id: distGenreMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: window.navigateToLibrarySearch(modelData.name)
                                    }
                                }
                            }
                        }
                    }
                }

                Rectangle { width: 1; Layout.fillHeight: true; color: Theme.glassBorder; Layout.topMargin: 20; Layout.bottomMargin: 20 }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    spacing: Theme.spacingMd
                    Text { text: "최다 보유 제작사"; font.pixelSize: 15; color: Theme.textSecondary; font.weight: Font.DemiBold }
                    AppScrollView {
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        contentWidth: availableWidth
                        Column {
                            width: parent.width; spacing: 2
                            Repeater {
                                model: tab.libraryDist.makers || []
                                Rectangle {
                                    width: parent.width
                                    height: distMakerInner.implicitHeight + 8
                                    radius: 4
                                    color: distMakerMa.containsMouse ? Qt.rgba(1,1,1,0.07) : "transparent"
                                    RowLayout {
                                        id: distMakerInner
                                        anchors { left: parent.left; right: parent.right; leftMargin: 4; rightMargin: 4; verticalCenter: parent.verticalCenter }
                                        spacing: 8
                                        Text {
                                            text: modelData.name
                                            font.pixelSize: 14
                                            color: distMakerMa.containsMouse ? "#48DBFB" : Theme.textPrimary
                                            Layout.fillWidth: true
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: modelData.count + "편"
                                            font.pixelSize: 13
                                            color: "#48DBFB"
                                            font.weight: Font.Bold
                                            Layout.preferredWidth: 60
                                            horizontalAlignment: Text.AlignRight
                                        }
                                    }
                                    MouseArea {
                                        id: distMakerMa
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: window.navigateToLibrarySearch(modelData.name)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        spacing: Theme.spacingMd

        RankedListCard {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            title: "선호 배우 TOP 5"
            icon: "❤"
            items: tab.actors
            maxItems: 5
            mode: "rank"
        }

        RankedListCard {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignTop
            title: "선호 장르 TOP 8"
            icon: "🎬"
            items: tab.genres
            maxItems: 8
            mode: "color"
            colorFn: tab.genreColor
        }
    }

    GlassCard {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        autoSize: false
        Layout.preferredHeight: tab.actorCollections.has_data
            ? Math.min(420, 80 + (tab.actorCollections.actors || []).length * 28)
            : 140

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.spacingMd
            spacing: Theme.spacingSm

            InsightSectionHeader {
                Layout.fillWidth: true
                icon: "🎭"
                title: "배우별 컬렉션 완성도"
                subtitle: "보유 작품 대비 완독"
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }

            AppScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: tab.actorCollections.has_data ? 280 : 48
                clip: true
                contentWidth: availableWidth
                ActorCollectionCard {
                    width: parent.width
                    collection: tab.actorCollections
                }
            }

            EmptyInsightHint {
                visible: !tab.actorCollections.has_data
                icon: "🎭"
                message: "완독률 데이터가 없습니다."
                hint: "보유 작품을 시청하면 표시됩니다."
            }
        }
    }

    CollapsibleInsightCard {
        Layout.fillWidth: true
        icon: "🏢"
        title: "선호 제작사 TOP 5"
        expanded: tab.makers.length > 0
        expandedHeight: Math.max(120, 80 + Math.ceil(tab.makers.length / 3) * 44)

        Flow {
            Layout.fillWidth: true
            visible: tab.makers.length > 0
            spacing: Theme.spacingSm
            Repeater {
                model: tab.makers.slice(0, 5)
                Rectangle {
                    radius: Theme.radiusSm
                    color: Theme.surfaceLight
                    border.color: Theme.glassBorder
                    border.width: 1
                    implicitWidth: makerChipRow.implicitWidth + Theme.spacingLg * 2
                    implicitHeight: 36
                    RowLayout {
                        id: makerChipRow
                        anchors.centerIn: parent
                        anchors.leftMargin: Theme.spacingMd
                        anchors.rightMargin: Theme.spacingMd
                        spacing: Theme.spacingSm
                        Text {
                            text: modelData.name || ""
                            font.pixelSize: Theme.fontCaption
                            color: Theme.textPrimary
                        }
                        Text {
                            text: modelData.score || 0
                            font.pixelSize: Theme.fontCaption
                            color: Theme.accentNeon
                            font.weight: Font.Bold
                        }
                    }
                }
            }
        }

        EmptyInsightHint {
            Layout.fillWidth: true
            visible: tab.makers.length === 0
            message: "제작사 데이터 없음"
        }
    }

    CollapsibleInsightCard {
        Layout.fillWidth: true
        icon: "⚙️"
        title: "파이프라인 리포트"
        subtitle: "최근 " + (tab.pipeline.days || 30) + "일 · 이벤트 "
            + (tab.pipeline.total_events || 0) + "건"
        expanded: false
        expandedHeight: 100

        Text {
            Layout.fillWidth: true
            text: "이벤트 " + (tab.pipeline.total_events || 0) + "건 · 오류 "
                + (tab.pipeline.error_events || 0) + "건 · 에러 JSON "
                + (tab.pipeline.error_json_files || 0) + "개"
            font.pixelSize: Theme.fontCaption
            color: Theme.textSecondary
            wrapMode: Text.Wrap
        }
    }

    Item { Layout.preferredHeight: Theme.spacingLg }
}
