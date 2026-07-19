import QtQuick

QtObject {
    function reveal(scroller, contentRoot, control, requestedMargin) {
        var flick = scroller ? scroller.contentItem : null
        if (!flick || !contentRoot || !control)
            return
        var point = control.mapToItem(contentRoot, 0, 0)
        var margin = requestedMargin === undefined ? 8 : requestedMargin
        var top = point.y - margin
        var bottom = point.y + control.height + margin
        var viewportHeight = scroller.availableHeight
        if (top < flick.contentY) {
            flick.contentY = Math.max(0, top)
        } else if (bottom > flick.contentY + viewportHeight) {
            var maximum = Math.max(0, flick.contentHeight - viewportHeight)
            flick.contentY = Math.min(maximum, bottom - viewportHeight)
        }
    }
}
