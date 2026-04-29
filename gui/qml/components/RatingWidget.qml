import QtQuick
import ".."

// ★×5 별점 위젯
// 사용법: RatingWidget { rating: 3; onRatingSelected: function(r) { ... } }
Item {
    id: root

    property int rating: 0      // 현재 별점 (0~5)
    property int hoverRating: 0 // 마우스 오버 미리보기
    property int maxRating: 5
    property int starSize: 22
    property bool interactive: true

    signal ratingSelected(int value)

    width: maxRating * (starSize + 4)
    height: starSize + 4

    Row {
        spacing: 4
        anchors.verticalCenter: parent.verticalCenter

        Repeater {
            model: root.maxRating

            Rectangle {
                id: starItem
                width: root.starSize
                height: root.starSize
                color: "transparent"

                property int starIndex: index + 1
                property bool filled: root.hoverRating > 0
                    ? root.hoverRating >= starIndex
                    : root.rating >= starIndex

                Text {
                    anchors.centerIn: parent
                    text: starItem.filled ? "★" : "☆"
                    font.pixelSize: root.starSize
                    color: starItem.filled
                        ? (root.hoverRating > 0 ? "#FFD700" : "#FFA500")
                        : Theme.textMuted

                    Behavior on color { ColorAnimation { duration: Theme.animFast } }

                    // 채워진 별에 미세 글로우
                    layer.enabled: starItem.filled
                    layer.effect: null
                }

                scale: starHover.containsMouse && root.interactive ? 1.2 : 1.0
                Behavior on scale { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutBack } }

                MouseArea {
                    id: starHover
                    anchors.fill: parent
                    hoverEnabled: root.interactive
                    cursorShape: root.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor

                    onEntered: if (root.interactive) root.hoverRating = starItem.starIndex
                    onExited:  if (root.interactive) root.hoverRating = 0
                    onClicked: {
                        if (!root.interactive) return
                        // 같은 별 재클릭 → 별점 초기화
                        var newRating = (root.rating === starItem.starIndex) ? 0 : starItem.starIndex
                        root.rating = newRating
                        root.ratingSelected(newRating)
                    }
                }
            }
        }
    }
}