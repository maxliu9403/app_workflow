"""
Live Debugger Module
====================

This module contains the Live Debugger (实时调试) functionality.
Currently implemented as methods in VintedAutomationConsole class.

## Methods that belong to this module:

### UI Building
- _build_live_tab()

### Screenshot & Drawing
- refresh_screenshot()
- redraw_screenshot()
- _draw_roi(roi: RoiPct)
- _draw_template_match_box()
- _draw_ocr_detections()
- _draw_offset_calculator()

### Canvas Events
- on_canvas_press(event)
- on_canvas_drag(event)
- on_canvas_release(event)
- _is_point_on_image(cx, cy)

### Coordinate Conversion
- _canvas_to_phone_px(cx, cy)
- _phone_px_to_canvas(x, y)
- _phone_px_to_pct(x, y)
- _pct_to_phone_px(x, y)
- _get_entries_roi()
- _get_current_roi_phone_px()
- schedule_draw_from_entries()
- draw_roi_from_entries()

### Coordinate Clipboard
- copy_current_coords()
- quick_copy_coordinates()
- copy_yaml_format()
- parse_quick_paste()

### OCR Functions
- _preprocess_for_text(bgr)
- _run_text_recognition(bgr, region_offset)
- extract_roi_text_show()
- extract_roi_text_copy()
- match_text_in_roi()
- clear_ocr_detections()
- test_ocr_roi()
- _format_rapidocr_result(result)

### Template Matching
- _preprocess_for_template(bgr, mode)
- choose_template_image()
- run_template_match()
- clear_template_match()

### Offset Calculator
- start_offset_calculator()
- clear_offset_calculator()
- _calculate_offset()

### Testing
- test_click_center()

### YAML Config
- load_yaml()
- save_yaml_selected()
- populate_tree()
- on_tree_select()
- choose_yaml_path()
- _init_treeview(parent)

## Future Refactoring
To extract these methods into a separate class:
1. Create a LiveDebuggerMixin class
2. Move all instance variables used by these methods to a shared base
3. Have VintedAutomationConsole inherit from LiveDebuggerMixin

This is a significant refactoring and should be done incrementally.
"""

# Placeholder for future LiveDebuggerMixin class
class LiveDebuggerMixin:
    """
    Mixin class for Live Debugger functionality.
    
    To use: Have VintedAutomationConsole inherit from this mixin.
    Currently not implemented - methods remain in main class.
    """
    pass
