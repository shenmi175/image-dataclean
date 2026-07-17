"""Explicit built-in tool manifest.

Each tool remains an independent package. Adding a built-in requires only one
manifest entry and does not require editing API or frontend navigation code.
"""

BUILTIN_TOOLS = (
    "backend.tools.video_frames:VideoFramesTool",
    "backend.tools.image_classifier:ImageClassifierTool",
    "backend.tools.labelme_to_yolo:LabelmeToYoloTool",
    "backend.tools.web_auto_export:WebAutoExportTool",
    "backend.tools.coco_to_labelme:CocoToLabelmeTool",
    "backend.tools.yolo_split:YoloSplitTool",
    "backend.tools.annotation_visualizer:AnnotationVisualizerTool",
    "backend.tools.yolo_merge:YoloMergeTool",
)
