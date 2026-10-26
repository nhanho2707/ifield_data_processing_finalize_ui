"""Interface language of the GUI: Vietnamese (the source text) or English.

tr() takes the Vietnamese text and returns it in the current language; {name} placeholders are
filled from keyword arguments. Text missing from EN is shown in Vietnamese.
"""

LANGUAGES = {"vi": "Tiếng Việt", "en": "English"}
DEFAULT = "vi"

_language = DEFAULT


def language() -> str:
    return _language


def set_language(code) -> None:
    global _language
    _language = code if code in LANGUAGES else DEFAULT


def tr(text: str, **values) -> str:
    if _language == "en":
        text = EN.get(text, text)
    return text.format(**values) if values else text


EN = {
    # --- Main window
    "Chọn một project": "Select a project",
    "Mở thư mục project": "Open project folder",
    "Ngôn ngữ giao diện": "Interface language",
    "Cấu hình": "Configuration",
    "Cấu hình •": "Configuration •",
    "Chạy xử lý": "Run processing",
    "Xuất SPSS": "SPSS export",
    "Codebook OE": "OE codebook",
    "Kiểm tra môi trường": "Check environment",
    "Cấu hình chưa lưu": "Unsaved configuration",
    "Lưu thay đổi cấu hình của {name}?": "Save the configuration changes of {name}?",
    "Chạy xử lý {name}": "Run processing {name}",
    "Đang chạy": "Running",
    "Một tác vụ đang chạy. Bấm \"Dừng\" và chờ tác vụ kết thúc trước khi thoát.":
        "A task is running. Click \"Stop\" and wait for it to finish before exiting.",
    "Một tác vụ đang chạy. Hãy chờ tác vụ kết thúc rồi đổi ngôn ngữ.":
        "A task is running. Wait for it to finish, then change the language.",

    # --- Sidebar
    "Đổi…": "Change…",
    "Chọn thư mục chứa các project": "Choose the folder containing the projects",
    "Tìm project…": "Search projects…",
    "+  Tạo project mới": "+  New project",
    "Làm mới": "Refresh",
    "● Đang kiểm tra Data Collection…": "● Checking Data Collection…",
    "● Data Collection: thiếu thành phần": "● Data Collection: components missing",
    "● Data Collection: sẵn sàng": "● Data Collection: ready",
    "Đủ các thành phần COM cần thiết.": "All required COM components are available.",
    "Tạo project mới": "New project",
    "Tên project (vd. VN2026100_ABC):": "Project name (e.g. VN2026100_ABC):",
    "Không tạo được project": "Could not create the project",
    "Đã tạo project": "Project created",
    "Đã tạo {path}\n\nChép file CSV vào source\\csv và file XML vào source\\xml, "
    "sau đó bấm \"Quét lại\" và \"Tự điền\" trong tab Cấu hình.":
        "Created {path}\n\nCopy the CSV files into source\\csv and the XML files into source\\xml, "
        "then click \"Rescan\" and \"Auto fill\" in the Configuration tab.",

    # --- Configuration
    "Tạo lại file MDD/DDF từ XML": "Rebuild the MDD/DDF files from XML",
    "run_mdd_source: xoá các file MDD/DDF/IVS/XLSX trong data rồi dựng lại từ XML.":
        "run_mdd_source: delete the MDD/DDF/IVS/XLSX files in data, then rebuild them from XML.",
    "Chỉ tạo lại file _EXPORT từ MDD có sẵn": "Only rebuild the _EXPORT file from the existing MDD",
    "run_mdd_export_source: dùng khi run_mdd_source tắt.": "run_mdd_export_source: used when run_mdd_source is off.",
    "Xoá toàn bộ dữ liệu cũ trước khi nạp": "Delete all existing data before loading",
    "delete_all: DELETE FROM VDATA trước khi nạp dữ liệu.": "delete_all: DELETE FROM VDATA before loading the data.",
    "Chỉ nạp dữ liệu test (_DefaultSP)": "Load test data only (_DefaultSP)",
    "dummy_data_required: bật = CHỈ nạp phiếu test; tắt = bỏ phiếu test.":
        "dummy_data_required: on = load ONLY the test interviews; off = skip the test interviews.",
    "Xoá phiếu huỷ / phiếu thừa": "Remove cancelled / extra interviews",
    "remove_all_ids: xoá các phiếu có _LoaiPhieu khác {_1,_5}.":
        "remove_all_ids: remove the interviews whose _LoaiPhieu is not {_1,_5}.",
    "Chạy làm sạch dữ liệu (CE)": "Run data cleaning (CE)",
    "run_ce_source: chạy dms\\CLEAN_DATA_SCRIPT.dms, tạo file _CE.":
        "run_ce_source: run dms\\CLEAN_DATA_SCRIPT.dms, creates the _CE file.",
    "Chạy xử lý câu mở (OE)": "Run open-ended processing (OE)",
    "run_oe_source: chạy dms\\CLEAN_DATA_PROCESSING.dms, tạo file _OE.":
        "run_oe_source: run dms\\CLEAN_DATA_PROCESSING.dms, creates the _OE file.",
    "Sửa config.json": "Edit config.json",
    "Dùng cho các mục nâng cao (cột thông tin đáp viên, axis_expression...). Thay đổi chỉ được ghi khi bấm Lưu.":
        "For advanced settings (respondent information columns, axis_expression...). "
        "Changes are written only when you click Save.",
    "JSON không hợp lệ": "Invalid JSON",
    "Dòng {line}, cột {column}: {message}": "Line {line}, column {column}: {message}",
    "Nội dung phải là một object { ... }.": "The content must be an object { ... }.",
    "Thông tin chung": "General",
    "Tên project (project_name)": "Project name (project_name)",
    "Ngôn ngữ mặc định": "Default language",
    "Quét lại": "Rescan",
    "Đọc lại source\\csv và source\\xml": "Read source\\csv and source\\xml again",
    "Tự điền": "Auto fill",
    "Ghép XML theo ProtoID trong tên file, đưa vào phần main và chọn ProtoID lớn nhất làm final.":
        "Match the XML files by the ProtoID in their name, put them in main and make the highest ProtoID final.",
    "Thêm stage": "Add stage",
    "Xoá stage cuối": "Remove last stage",
    "Số dòng CSV": "CSV rows",
    "File XML": "XML file",
    "Phần": "Section",
    "Nguồn dữ liệu (ProtoID trong CSV ↔ file XML)": "Data sources (ProtoID in CSV ↔ XML file)",
    "Final: phiên bản XML dùng để dựng MDD của phần đó. Các stage follow-up được nạp vào vòng lặp Phase.":
        "Final: the XML version used to build the MDD of that section. "
        "The follow-up stages are loaded into the Phase loop.",
    "Tuỳ chọn xử lý": "Processing options",
    "Kiểm tra": "Check",
    "Sửa JSON…": "Edit JSON…",
    "Hoàn tác": "Revert",
    "Kiểm tra config, file nguồn và môi trường Data Collection mà không xử lý gì.":
        "Check the configuration, the source files and the Data Collection environment without processing anything.",
    "Lưu": "Save",
    "Không đọc được config.json": "Could not read config.json",
    "ProtoID này không có dữ liệu trong CSV": "This ProtoID has no data in the CSV files",
    "— Không dùng —": "— Not used —",
    "Đang đọc CSV…": "Reading CSV…",
    "{protos} ProtoID trong CSV · {rows} dòng · {xmls} file XML": "{protos} ProtoIDs in CSV · {rows} rows · {xmls} XML files",
    "Đọc file CSV": "Read CSV files",
    "Không xoá được": "Cannot remove",
    "Còn ProtoID đang gán cho {stage}. Hãy bỏ gán trước.": "Some ProtoIDs are still assigned to {stage}. Unassign them first.",
    "Không lưu được": "Could not save",
    "Kiểm tra: đang chạy…": "Check: running…",
    "Kiểm tra: {count} lỗi": "Check: {count} errors",
    "Kiểm tra: sẵn sàng chạy": "Check: ready to run",
    "Kiểm tra: sẵn sàng chạy (có cảnh báo)": "Check: ready to run (with warnings)",
    "Không có lỗi.": "No errors.",
    "Kiểm tra {name}": "Check {name}",
    "Kiểm tra: lỗi": "Check: failed",

    # --- Run
    "Đọc file CSV / XML": "Read CSV / XML files",
    "Tạo file MDD/DDF": "Build the MDD/DDF files",
    "Nạp dữ liệu phần main": "Load the main data",
    "Xuất thông tin đáp viên (RESPONDENT.xlsx)": "Export respondent information (RESPONDENT.xlsx)",
    "Nạp dữ liệu các stage follow-up": "Load the follow-up stages",
    "Kiểm tra update_data.csv": "Check update_data.csv",
    "Áp dụng update_data.csv": "Apply update_data.csv",
    "Làm sạch dữ liệu (CE)": "Data cleaning (CE)",
    "Xử lý câu mở (OE)": "Open-ended processing (OE)",
    "Chờ": "Pending",
    "Tắt trong cấu hình": "Off in the configuration",
    "Đang chạy…": "Running…",
    "Xong": "Done",
    "Bỏ qua (không có dữ liệu)": "Skipped (no data)",
    "Lỗi": "Error",
    "Đã dừng": "Stopped",
    "▶  Chạy xử lý": "▶  Run processing",
    "Bước": "Step",
    "Trạng thái": "Status",
    "Thời gian": "Time",
    "Các bước (bật/tắt trong tab Cấu hình)": "Steps (turned on/off in the Configuration tab)",
    "File trong data": "Files in data",
    "Kích thước": "Size",
    "Sửa lúc": "Modified",
    "Mở thư mục data": "Open data folder",
    "Mở log gần nhất": "Open latest log",
    "Kết quả (nháy đúp để mở)": "Results (double-click to open)",
    "Cấu hình chưa lưu: sẽ tự lưu khi chạy": "Unsaved configuration: it will be saved when the run starts",
    "✔ Hoàn tất sau {minutes}m{seconds}s": "✔ Completed in {minutes}m{seconds}s",
    "■ Đã dừng": "■ Stopped",

    # --- Log
    "Nhật ký": "Log",
    "Dừng": "Stop",
    "Dừng sau dòng dữ liệu hiện tại. Một bước DMS đang chạy sẽ chạy xong rồi mới dừng.":
        "Stop after the current data row. A DMS step that is running finishes before stopping.",
    "Xoá": "Clear",
    "✔ {title}: xong": "✔ {title}: done",
    "■ {title}: đã dừng": "■ {title}: stopped",
    "✖ {title}: lỗi": "✖ {title}: failed",
    "Đang dừng…": "Stopping…",

    # --- Codebook
    "Chọn…": "Browse…",
    "Nhãn ghi vào kết quả cùng với mã": "Label written to the result with the code",
    "Nội dung được tìm trong các cột label_<n> của sheet punch (không phân biệt hoa thường)":
        "Text searched for in the label_<n> columns of the punch sheet (case-insensitive)",
    "File coding": "Coding file",
    "File Excel": "Excel file",
    "Sheet codebook": "Codebook sheet",
    "Sheet punch": "Punch sheet",
    "Cột mã": "Code column",
    "Cột nhãn kết quả": "Result label column",
    "Cột dùng để so khớp": "Matching column",
    "Cột ID đáp viên": "Respondent ID column",
    "Với mỗi cột label_&lt;n&gt; của sheet punch, thêm cột label_&lt;n&gt;_ipsos = (mã, nhãn) của dòng codebook "
    "đầu tiên có nội dung \"cột so khớp\" nằm trong nhãn đã code. Kết quả lưu thành &lt;tên file&gt;_coding.xlsx cùng thư mục.":
        "For each label_&lt;n&gt; column of the punch sheet, adds a label_&lt;n&gt;_ipsos column = (code, label) of the "
        "first codebook row whose \"matching column\" text is found in the coded label. The result is saved as "
        "&lt;file name&gt;_coding.xlsx in the same folder.",
    "Tạo file coding": "Create coding file",
    "Mở file": "Open file",
    "Chọn file coding": "Choose the coding file",
    "✖ Không đọc được file: {error}": "✖ Could not read the file: {error}",
    "✔ Đã lưu {name}": "✔ Saved {name}",
    "✖ Lỗi, xem nhật ký bên dưới": "✖ Error, see the log below",

    # --- SPSS
    "Chọn file khác…": "Choose another file…",
    "Tải danh sách câu hỏi": "Load question list",
    "Ví dụ: SELECT * FROM VDATA WHERE Respondent_serial = '6823050106491224'":
        "Example: SELECT * FROM VDATA WHERE Respondent_serial = '6823050106491224'",
    "Nguồn": "Source",
    "File MDD": "MDD file",
    "File DDF": "DDF file",
    "Câu truy vấn": "Query",
    "Lọc câu hỏi…": "Filter questions…",
    "Chọn tất cả (đang hiện)": "Select all (shown)",
    "Bỏ chọn tất cả": "Deselect all",
    "Dán danh sách…": "Paste list…",
    "Dán tên câu hỏi, mỗi dòng một câu (vd. copy từ danh sách cũ trong spss_processing.py)":
        "Paste question names, one per line (e.g. copied from the old list in spss_processing.py)",
    "Câu hỏi xuất ra SPSS (thứ tự theo MDD)": "Questions exported to SPSS (in MDD order)",
    "Xuất SPSS (.sav)": "Export SPSS (.sav)",
    "Mở thư mục": "Open folder",
    "Chọn file MDD": "Choose the MDD file",
    "{name} không tồn tại": "{name} does not exist",
    "Đọc danh sách câu hỏi {name}": "Read question list {name}",
    "Chưa có danh sách": "No question list",
    "Bấm \"Tải danh sách câu hỏi\" trước.": "Click \"Load question list\" first.",
    "Dán danh sách câu hỏi": "Paste question list",
    "Mỗi dòng một tên câu hỏi:": "One question name per line:",
    "Không tìm thấy": "Not found",
    "Các câu hỏi sau không có trong MDD:\n": "These questions are not in the MDD:\n",
    "Đã chọn {checked}/{total}": "Selected {checked}/{total}",
    " — không chọn câu nào = xuất toàn bộ": " — none selected = export everything",
    "Xuất toàn bộ?": "Export everything?",
    "Chưa chọn câu hỏi nào. Xuất tất cả các câu hỏi không bị ẩn?":
        "No question is selected. Export all the questions that are not hidden?",
    "Đang xuất…": "Exporting…",
    "Xuất SPSS {name}": "SPSS export {name}",
}
