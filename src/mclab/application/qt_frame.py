"""Qt image-provider factory kept lazy for headless installations."""

from __future__ import annotations

from typing import Any


def create_frame_provider(provider_type: Any, image_type: Any) -> type:
    """Build the MuJoCo frame provider after Qt has been selected by the CLI."""

    class FrameProvider(provider_type):
        def __init__(self) -> None:
            super().__init__(provider_type.Image)
            self.image = image_type(960, 540, image_type.Format_RGB888)
            self.image.fill(0x111827)

        def update(self, array: Any) -> None:
            if array is None or not hasattr(array, "shape") or len(array.shape) != 3:
                return
            height, width, channels = array.shape
            if channels < 3:
                return
            stride = int(array.strides[0])
            self.image = image_type(
                array.data, width, height, stride, image_type.Format_RGB888
            ).copy()

        def requestImage(self, _id: str, size: Any, _requested_size: Any) -> Any:  # noqa: N802
            image = self.image
            size.setWidth(image.width())
            size.setHeight(image.height())
            return image

    return FrameProvider
