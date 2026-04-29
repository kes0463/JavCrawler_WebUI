import QtQuick
import QtQuick.Controls
import ".."

ScrollView {
    Component.onCompleted: {
        var f = contentItem
        if (f) {
            f.boundsBehavior       = Flickable.StopAtBounds
            f.flickDeceleration    = Theme.flickDeceleration
            f.maximumFlickVelocity = Theme.maxVelocity
        }
    }
}
