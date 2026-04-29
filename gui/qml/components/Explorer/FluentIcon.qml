import QtQuick
import QtQuick.Shapes
import "../../"

Item {
    id: root
    property string type: "folder" // folder, home, drive, pc, desktop, downloads, documents, pictures, videos
    property color color: Theme.accentNeon
    property real size: 24

    width: size
    height: size

    // SVG 데이터 맵
    readonly property var iconPaths: {
        "folder": "M2 4 C 2 2.89 2.89 2 4 4 L 10 4 L 12 6 L 20 6 C 21.11 6 22 6.89 22 8 L 22 18 C 22 19.11 21.11 20 20 20 L 4 20 C 2.89 20 2 19.11 2 18 L 2 4 Z",
        "home": "M10 20 L 10 14 L 14 14 L 14 20 L 19 20 L 19 12 L 22 12 L 12 3 L 2 12 L 5 12 L 5 20 L 10 20 Z",
        "drive": "M2 6 C 2 4.89 2.89 4 4 4 L 20 4 C 21.11 4 22 4.89 22 6 L 22 18 C 22 19.11 21.11 20 20 20 L 4 20 C 2.89 20 2 19.11 2 18 L 2 6 Z M 4 16 L 20 16 L 20 18 L 4 18 L 4 16 Z M 17 17 C 17 17.55 17.45 18 18 18 C 18.55 18 19 17.55 19 17 C 19 16.45 18.55 16 18 16 C 17.45 16 17 16.45 17 17 Z",
        "pc": "M21 2 H 3 C 1.9 2 1 2.9 1 4 V 16 C 1 17.1 1.9 18 3 18 H 10 V 20 H 8 V 22 H 16 V 20 H 14 V 18 H 21 C 22.1 18 23 17.1 23 16 V 4 C 23 2.9 22.1 2 21 2 Z M 21 16 H 3 V 4 H 21 V 16 Z",
        "desktop": "M21 2 H 3 C 1.9 2 1 2.9 1 4 V 16 C 1 17.1 1.9 18 3 18 H 10 V 20 H 8 V 22 H 16 V 20 H 14 V 18 H 21 C 22.1 18 23 17.1 23 16 V 4 C 23 2.9 22.1 2 21 2 Z",
        "downloads": "M19 9 H 15 V 3 H 9 V 9 H 5 L 12 16 L 19 9 Z M 5 18 V 20 H 19 V 18 H 5 Z",
        "documents": "M14 2 H 6 C 4.9 2 4 2.9 4 4 V 20 C 4 21.1 4.9 22 6 22 H 18 C 19.1 22 20 21.1 20 20 V 8 L 14 2 Z M 13 9 V 3.5 L 18.5 9 H 13 Z",
        "pictures": "M21 19 V 5 C 21 3.9 20.1 3 19 3 H 5 C 3.9 3 3 3.9 3 5 V 19 C 3 20.1 3.9 21 5 21 H 19 C 20.1 21 21 20.1 21 19 Z M 8.5 13.5 L 11 16.51 L 14.5 12 L 19 18 H 5 L 8.5 13.5 Z",
        "videos": "M18 4 L 20 8 H 17 L 15 4 H 13 L 15 8 H 12 L 10 4 H 8 L 10 8 H 7 L 5 4 H 4 C 2.9 4 2 4.9 2 6 V 18 C 2 19.1 2.9 20 4 20 H 20 C 21.1 20 22 19.1 22 18 V 4 H 18 Z",
        "chevron-right": "M10 6 L 8.59 7.41 L 13.17 12 L 8.59 16.59 L 10 18 L 16 12 L 10 6 Z",
        "chevron-down": "M16.59 8.59 L 12 13.17 L 7.41 8.59 L 6 10 L 12 16 L 18 10 L 16.59 8.59 Z",
        "back": "M20 11 H 7.83 L 13.42 5.41 L 12 4 L 4 12 L 12 20 L 13.41 18.59 L 7.83 13 H 20 V 11 Z",
        "forward": "M12 4 L 10.59 5.41 L 16.17 11 H 4 V 13 H 16.17 L 10.59 18.59 L 12 20 L 20 12 L 12 4 Z",
        "up": "M4 12 L 12 4 L 20 12 L 18.59 13.41 L 13 7.83 V 20 H 11 V 7.83 L 5.41 13.41 L 4 12 Z",
        "check": "M9 16.17 L 4.83 12 L 3.41 13.41 L 9 19 L 21 7 L 19.59 5.59 L 9 16.17 Z",
        "view-grid": "M3 11 H 11 V 3 H 3 V 11 Z M 13 3 V 11 H 21 V 3 H 13 Z M 3 21 H 11 V 13 H 3 V 21 Z M 13 21 H 21 V 13 H 13 V 21 Z",
        "view-list": "M3 14 H 21 V 11 H 3 V 14 Z M 3 19 H 21 V 16 H 3 V 19 Z M 3 9 H 21 V 6 H 3 V 9 Z",
        "plus": "M19 13 H 13 V 19 H 11 V 13 H 5 V 11 H 11 V 5 H 13 V 11 H 19 V 13 Z",
        "sort": "M3 18 H 9 V 16 H 3 V 18 Z M 3 6 V 8 H 21 V 6 H 3 Z M 3 13 H 15 V 11 H 3 V 13 Z"
    }

    Shape {
        anchors.fill: parent
        vendorExtensionsEnabled: true
        
        ShapePath {
            fillColor: root.color
            strokeColor: "transparent"
            PathSvg {
                path: iconPaths[root.type] || iconPaths["folder"]
            }
        }
    }
}