<h3>iField data processing</h3>

## Ứng dụng desktop

Yêu cầu: máy đã cài IBM SPSS Data Collection (bản 64-bit).

- Người dùng: chạy `iFieldDataProcessing-Setup-<version>.exe` (không cần quyền admin), sau đó mở
  **iField Data Processing** từ Start Menu. Cài bản mới hơn sẽ tự nâng cấp bản cũ; gỡ trong Settings → Apps.
  Lần đầu, bấm **Đổi…** ở góc trên bên trái để chọn thư mục chứa các project.
  (Bản `iFieldDataProcessing-<version>.zip` dùng được mà không cần cài: giải nén rồi mở `iField Data Processing.exe`.)
- Lập trình viên: `pip install -r requirements.txt` rồi `python ifield_app.py`.

Các tab: **Cấu hình** (ghép ProtoID trong CSV với file XML, tuỳ chọn xử lý, Kiểm tra) ·
**Chạy xử lý** (các bước, tiến độ, nút Dừng, file kết quả) · **Xuất SPSS** (chọn câu hỏi từ MDD) · **Codebook OE**.
Ngôn ngữ giao diện (Tiếng Việt / English): ô chọn ở góc trên bên phải.

`source\update_data.csv` (InstanceID, Question Name, Previous Value, Current Value): mỗi dòng sửa một câu của một
phiếu. Câu chọn code ghi `{_5}` hoặc `"{_1,_2}"` (có dấu phẩy thì để trong ngoặc kép); để trống Current Value để xoá
giá trị. Một câu có nhiều dòng thì lấy dòng cuối. Trước khi nạp dữ liệu, mọi dòng được kiểm tra với file `_EXPORT.mdd`
(InstanceID có trong dữ liệu, tên câu có trong MDD, code có trong danh sách, số code của câu single/multi, code loại trừ,
số/ngày hợp lệ và trong khoảng). Có lỗi thì không nạp/update gì, báo cáo lưu ở `logs\update_data_check_<thời gian>.xlsx`.
Nút **Kiểm tra** cũng chạy bước này khi đã có `_EXPORT.mdd`.

Tuỳ chọn của file exe:

```
"iField Data Processing.exe" --self-test report.txt      # kiểm tra cài đặt (Data Collection, DLL SPSS, Excel, Qt)
"iField Data Processing.exe" --cli run VN2025100_ABC     # chạy không mở cửa sổ (log trong projects\<project>\logs)
```

### Build

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

Tạo `dist\iFieldDataProcessing\`, tự chạy `--self-test`, nén thành `dist\iFieldDataProcessing-<version>.zip`
và tạo bộ cài `dist\iFieldDataProcessing-Setup-<version>.exe` (`installer.iss`). Bộ cài cần Inno Setup trên máy build:
`winget install JRSoftware.InnoSetup --scope user`.

Phát hành bản mới: ghi thay đổi vào `CHANGELOG.md`, tăng `__version__` trong `app/__init__.py` rồi build lại. Icon: `python tools/make_icon.py`.

## Cấu trúc code

- `app/core/` — toàn bộ logic xử lý, không phụ thuộc giao diện (dùng chung cho CLI và GUI)
  - `pipeline.py` — các bước xử lý (trước đây là `ifield_processing.py`)
  - `preflight.py` — kiểm tra config.json và file nguồn trước khi chạy
  - `sql_builder.py` — chuyển dòng CSV thành câu lệnh SQL
  - `spss_export.py`, `codebook.py` — trước đây là `spss_processing.py`, `ifield_codebook_format.py`
  - `reporter.py` — log / tiến độ / dừng, nối core với CLI hoặc GUI
- `app/gui/` — giao diện PySide6 (mỗi tab một file, `jobs.py` chạy tác vụ nền, `i18n.py` bản dịch tiếng Anh)
- `app/cli.py` — giao diện dòng lệnh
- `object/` — thư viện đọc XML iField và thao tác MDD/DDF
- `ifield.spec`, `build.ps1`, `installer.iss` — đóng gói

## Chạy bằng dòng lệnh

```
python -m app list                         # danh sách project trong thư mục projects
python -m app new VN2025100_ABC            # tạo project mới từ VNXXXXXXX_TEMPLATE
python -m app check VN2025100_ABC          # kiểm tra config + file nguồn, không xử lý gì
python -m app run VN2025100_ABC            # chạy toàn bộ (log lưu ở projects\<project>\logs)
python -m app spss VN2025100_ABC --mdd data\X_EXPORT.mdd --ddf data\X_EXPORT.ddf -q Q1 Q2
python -m app codebook "projects\VN2025100_ABC\data\oe\Q9 manual_report.xlsx"
```

Cách cũ vẫn dùng được: sửa `project_name` trong `ifield_processing.py` rồi chạy file đó.

Chạy test: `python -m unittest discover -s tests -t .`

<blockquote>
<p><b>Step 1</b>: Enter the project name to process the data</p>

<pre>
    <code>
        #Enter the project name to process the data
        project_name = "VN2024001_F2F_TEST"
    </code>
</pre>

<p><b>Step 2</b>: To see local branch</p>

<pre>
    <code>
        git branch
    </code>
</pre>

<p><b>Step 3</b>: To create and move to a new local branch</p>

<pre>
    <code>
        git branch -b my-branch-name
    </code>
</pre>

<u>Note</u>: replace <b>my-branch-name</b> with whatever name you want

<p><b>Step 4</b>: Setup config.json</p>

<ol>
    <li><b>project_name</b>: Enter a project name</li>
    <li><b>run_mdd_source</b>: Select TRUE to create an original mdd/ddf file or FALSE to skip this step.</li>
</ol>

<p><b>Step 5</b>: Setup for the F2F/CLT/CATI (optional)</p>

<ol>
    <li><b>default_language: Default the language that is used as the default</b></li>
    <li><b>delete_all</b>: Delete all data before inserting new data (default is FALSE)</li>
    <li><b>dummy_data_required</b>: Allow inserting dummy data (default is FALSE)
    <li><b>remove_all_ids</b>: Remove all IDs with types of cancel and extra (default is TRUE)
</ol>

<p><b>Step 6</b>: Setup for the F2F/CLT/CATI</p>

<ol>
    <li>
        <b>main</b>:
        <ul>
            <li>
                <b>xmls</b>: Fill in the information for the project's XML files (from the old version to the new version) according to the syntax:
                <pre>
                    <code>
                        "protodid": "file_name.xml"
                    </code>
                </pre>
            </li>
            <li><b>protoid_final</b>: Protoid is used fo create the file original mdd/ddf file</li>
        <ul>
    </li>
</ol>
</blockquote>

<pre>
    <code>
        {
            "project_name" : "--Enter a project name--",
            "run_mdd_source" : true, 
            "main" : {
                "xmls" : {
                    "--Enter a protodid 1--" : "--Enter a xml file--",
                    "--Enter a protodid 2--" : "--Enter a xml file--"
                },
                "protoid_final" : "--Enter a protoid final 2--"
            },
            "stages" : {
                "stage-1" : {
                    "xmls" : {
                        "--Enter a protodid 1--" : "--Enter a xml file--",
                        "--Enter a protodid 2--" : "--Enter a xml file--"
                    },
                    "protoid_final" : "--Enter a protoid final 2--"
                },
                "stage-2" : {
                    "xmls" : {
                        "--Enter a protodid 1--" : "--Enter a xml file--",
                        "--Enter a protodid 2--" : "--Enter a xml file--"
                    },
                    "protoid_final" : "--Enter a protoid final 2--"
                },
                "stage-3" : {
                    "xmls" : {
                        "--Enter a protodid 1--" : "--Enter a xml file--",
                        "--Enter a protodid 2--" : "--Enter a xml file--"
                    },
                    "protoid_final" : "--Enter a protoid final 2--"
                }
            }
        }
    </code>
</pre>