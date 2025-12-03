import os
import subprocess
import logging
from pathlib import Path
from flask import Flask, request, render_template_string, send_from_directory, flash, redirect, url_for
from werkzeug.utils import secure_filename

# --- 配置 ---
UPLOAD_FOLDER_LINUX = '/app/shared_data/uploads'
CONVERTED_FOLDER_LINUX = '/app/shared_data/converted'
# msconvert.exe 在 Wine C: 驱动器中的路径
MSCONVERT_EXE_WINE_PATH = "C:\\pwiz\\msconvert.exe" 
# 允许上传的文件扩展名
ALLOWED_EXTENSIONS = {'raw', 'wiff', 'd', 'mzml', 'mzxml'} 

# --- Flask 应用初始化 ---
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER_LINUX
app.config['CONVERTED_FOLDER'] = CONVERTED_FOLDER_LINUX
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 例如：2 GB 上传限制
app.secret_key = os.urandom(24) # 用于 flash 消息

# --- 日志配置 ---
# Ensure logger is configured before any logging calls
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# For Flask's own logger, if you want to use it:
# app.logger.setLevel(logging.DEBUG) 
# handler = logging.StreamHandler()
# handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
# app.logger.addHandler(handler)


# --- 确保目录存在 ---
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
Path(app.config['CONVERTED_FOLDER']).mkdir(parents=True, exist_ok=True)
app.logger.info(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
app.logger.info(f"Converted folder: {app.config['CONVERTED_FOLDER']}")


# --- 辅助函数 ---
def allowed_file(filename):
    """
    Check if the filename has an allowed extension.
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def linux_to_wine_path(linux_path):
    """
    Converts a Linux absolute path to a Wine path (e.g., /foo/bar -> Z:\foo\bar).
    """
    linux_path_str = str(linux_path)
    wine_style_path_segment = linux_path_str.replace('/', '\\')
    wine_path = f"Z:{wine_style_path_segment}"
    # app.logger.debug(f"Converted Linux path '{linux_path_str}' to Wine path '{wine_path}'")
    return wine_path


# --- HTML 模板 (内联) ---
INDEX_HTML = """
<!doctype html>
<html lang="zh">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>文件转换器 (Flask)</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background-color: #f4f4f4; color: #333; }
        .container { background-color: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); max-width: 800px; margin: auto;}
        h1, h2 { color: #333; }
        .flash-messages { padding-left: 0; }
        .flash-messages li { list-style: none; padding: 10px; margin-bottom: 10px; border-radius: 4px; }
        .flash-success { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .flash-error { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="file"], input[type="submit"] { padding: 10px; border-radius: 4px; border: 1px solid #ddd; width: calc(100% - 22px); margin-bottom: 10px;}
        input[type="submit"] { background-color: #007bff; color: white; cursor: pointer; width: auto; }
        input[type="submit"]:hover { background-color: #0056b3; }
        .output { margin-top: 20px; padding: 10px; background-color: #e9ecef; border: 1px solid #ced4da; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; max-height: 400px; overflow-y: auto; font-family: monospace;}
        .download-link { display: inline-block; margin-top: 10px; padding: 10px 15px; background-color: #28a745; color: white; text-decoration: none; border-radius: 4px; }
        .download-link:hover { background-color: #218838; }
    </style>
</head>
<body>
    <div class="container">
        <h1>文件转换器 (Flask + msconvert)</h1>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            <ul class="flash-messages">
            {% for category, message in messages %}
              <li class="flash-{{ category }}">{{ message }}</li>
            {% endfor %}
            </ul>
          {% endif %}
        {% endwith %}

        <h2>1. 上传文件或目录</h2>
        <form method="post" action="{{ url_for('upload_and_convert_file') }}" enctype="multipart/form-data">
            <div class="form-group">
                <label>选择上传类型:</label>
                <input type="radio" id="type_file" name="upload_type" value="file" checked onchange="toggleUpload(this.value)">
                <label for="type_file" style="display: inline-block; margin-right: 15px;">单个文件 (.raw, .wiff)</label>
                
                <input type="radio" id="type_folder" name="upload_type" value="folder" onchange="toggleUpload(this.value)">
                <label for="type_folder" style="display: inline-block;">文件夹 (.d)</label>
            </div>

            <div class="form-group">
                <label for="file">选择文件或目录:</label>
                <input type="file" name="file" id="file" required>
                <small id="upload_note" style="display:none;">注意: 目录上传功能仅在部分浏览器 (如 Chrome, Firefox) 中受支持。</small>
            </div>
            <input type="submit" value="上传并开始转换">
        </form>

        <script>
            function toggleUpload(uploadType) {
                var fileInput = document.getElementById('file');
                var uploadNote = document.getElementById('upload_note');
                if (uploadType === 'folder') {
                    fileInput.setAttribute('webkitdirectory', '');
                    fileInput.setAttribute('mozdirectory', '');
                    fileInput.setAttribute('directory', '');
                    uploadNote.style.display = 'block';
                } else {
                    fileInput.removeAttribute('webkitdirectory');
                    fileInput.removeAttribute('mozdirectory');
                    fileInput.removeAttribute('directory');
                    uploadNote.style.display = 'none';
                }
                // Reset file input to clear selection
                fileInput.value = '';
            }
            // Initialize on page load
            toggleUpload('file');
        </script>

        {% if converted_file_download_name %}
        <h2>2. 下载结果</h2>
        <a href="{{ url_for('download_file', filename=converted_file_download_name) }}" class="download-link">下载 {{ converted_file_display_name }}</a>
        {% endif %}

        {% if command_output %}
        <h2>命令输出 (调试用):</h2>
        <pre class="output">{{ command_output }}</pre>
        {% endif %}
    </div>
</body>
</html>
"""

# --- Flask 路由 ---
@app.route('/', methods=['GET'])
def index():
    # Render the HTML template string
    return render_template_string(INDEX_HTML)

@app.route('/upload-convert', methods=['POST'])
def upload_and_convert_file():
    # Initialize variables for rendering template even on error
    converted_file_download_name = None
    converted_file_display_name = None
    command_output_display = None
    
    files = request.files.getlist('file')

    if not files or files[0].filename == '':
        flash('未选择文件或目录', 'error')
        return redirect(url_for('index'))

    # Check if a directory was uploaded (by inspecting the relative path)
    is_directory_upload = False
    if len(files) > 1 and files[0].filename.startswith('.'):
        # A heuristic for directory uploads from webkit browsers
        # The first file is often a hidden file like .DS_Store
        # A better check is to see if there's a common base directory
        dir_name = Path(files[0].filename).parts[0]
        if all(f.filename.startswith(dir_name) for f in files):
            is_directory_upload = True
            
    # For single file uploads, the first file is the one we want
    upload_item = files[0]
    
    # Heuristic to detect if a directory was intended to be uploaded
    # webkitdirectory posts multiple files with paths
    if len(files) > 1 and any('/' in f.filename for f in files):
        is_directory_upload = True

    if is_directory_upload:
        # It's a directory upload, get the base directory name
        # The paths are like "folder/file.txt", so we extract "folder"
        dir_name = secure_filename(Path(files[0].filename).parts[0])
        
        # Validate the directory name
        if not dir_name.endswith('.d'):
            flash('不允许的目录类型。目录必须以 ".d" 结尾。', 'error')
            return redirect(url_for('index'))

        linux_input_path = Path(app.config['UPLOAD_FOLDER']) / dir_name
        linux_input_path.mkdir(exist_ok=True)
        
        for file in files:
            # Recreate directory structure within the upload folder
            relative_path = Path(file.filename)
            save_path = Path(app.config['UPLOAD_FOLDER']) / relative_path
            save_path.parent.mkdir(parents=True, exist_ok=True)
            file.save(save_path)
            
        original_filename = dir_name
        linux_input_filepath = linux_input_path
        
    else: # Single file upload
        file = files[0]
        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            linux_input_filepath = Path(app.config['UPLOAD_FOLDER']) / original_filename
            file.save(linux_input_filepath)
        else:
            flash('不允许的文件类型', 'error')
            return redirect(url_for('index'))
            

    try:
        app.logger.info(f"文件/目录已上传并保存到: {linux_input_filepath}")
        flash(f"'{original_filename}' 上传成功。", "success")

        # --- 开始转换 ---
        status_message = "正在转换文件，请稍候..."
        app.logger.info(status_message)
        
        wine_input_file_path = linux_to_wine_path(str(linux_input_filepath))
        linux_converted_dir = Path(app.config['CONVERTED_FOLDER'])
        wine_output_dir_path = linux_to_wine_path(str(linux_converted_dir))

        app.logger.info(f"Wine 输入文件路径: {wine_input_file_path}")
        app.logger.info(f"Wine 输出目录路径: {wine_output_dir_path}")

        msconvert_exe_args = [
            wine_input_file_path, 
            "-o", wine_output_dir_path,         
            "--mzML",
            "--filter", "peakPicking true 1-",
            "--filter", "msLevel 1-"
        ]
        
        # Construct WINEPATH string separately to avoid f-string backslash issue
        winepath_value = os.getenv('WINEPATH', 'C:\\pwiz;C:\\pwiz\\skyline')
        winedebug_value = os.getenv('WINEDEBUG', '+warn,+fixme')

        command_parts = [
            "/usr/bin/sudo",
            "/usr/bin/env",
            "WINEPREFIX=/wineprefix64",
            f"WINEPATH={winepath_value}", # Use the pre-constructed string
            f"WINEDEBUG={winedebug_value}", 
            "/usr/bin/xvfb-run", "-a",
            "/usr/bin/wine",
            MSCONVERT_EXE_WINE_PATH, 
        ]
        command_parts.extend(msconvert_exe_args)

        full_command_str_for_log = " ".join([f"'{part}'" if " " in part or ":" in part or "=" in part else part for part in command_parts])
        app.logger.info(f"准备执行命令: {full_command_str_for_log}")
        
        # Use subprocess.run for better control and error handling
        result = subprocess.run(command_parts, capture_output=True, text=True, timeout=300)
        
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

        command_output_display = (
            f"Command Executed: {full_command_str_for_log}\n"
            f"Exit Code: {exit_code}\n"
            f"--- STDOUT ---\n{stdout}\n"
            f"--- STDERR ---\n{stderr}"
        )
        app.logger.info(f"命令 STDOUT: {stdout}")
        if stderr:
            app.logger.warning(f"命令 STDERR: {stderr}")

        output_filename_base = Path(original_filename).stem
        expected_converted_filename_mzml = f"{output_filename_base}.mzML"
        linux_expected_output_filepath = linux_converted_dir / expected_converted_filename_mzml

        if exit_code == 0 and linux_expected_output_filepath.is_file():
            flash(f"文件 '{original_filename}' 转换成功！", "success")
            app.logger.info(f"转换成功。输出文件: {linux_expected_output_filepath}")
            converted_file_download_name = expected_converted_filename_mzml
            converted_file_display_name = expected_converted_filename_mzml
        else:
            error_msg = f"转换失败。退出码: {exit_code}."
            flash(error_msg, "error")
            app.logger.error(f"{error_msg} Expected file: {linux_expected_output_filepath}, Exists: {linux_expected_output_filepath.is_file()}")
    
    except subprocess.TimeoutExpired:
        error_msg = "转换超时！"
        flash(error_msg, 'error')
        app.logger.error(error_msg)
        command_output_display = error_msg
    except Exception as e:
        error_msg = f"处理文件时发生错误: {str(e)}"
        flash(error_msg, 'error')
        app.logger.exception("处理文件时发生错误")
        command_output_display = error_msg
    
    return render_template_string(INDEX_HTML, 
                                  converted_file_download_name=converted_file_download_name,
                                  converted_file_display_name=converted_file_display_name,
                                  command_output=command_output_display)

@app.route('/download/<path:filename>') # Use path converter for filenames with extensions
def download_file(filename):
    safe_filename = secure_filename(filename)
    if not safe_filename: 
        flash('无效的文件名', 'error')
        return redirect(url_for('index'))
        
    try:
        app.logger.info(f"请求下载文件: {safe_filename} 从目录: {app.config['CONVERTED_FOLDER']}")
        return send_from_directory(app.config['CONVERTED_FOLDER'],
                                   safe_filename, as_attachment=True)
    except FileNotFoundError:
        flash('文件未找到，无法下载。', 'error')
        app.logger.error(f"下载请求：文件未找到 {Path(app.config['CONVERTED_FOLDER']) / safe_filename}")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'下载文件时发生错误: {str(e)}', 'error')
        app.logger.exception(f"下载文件时发生错误: {safe_filename}")
        return redirect(url_for('index'))

if __name__ == '__main__':
    # This part is for direct execution (e.g., python app.py)
    # Dockerfile uses `flask run` which handles this differently.
    app.run(debug=True, host='0.0.0.0', port=5000)
