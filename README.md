## 🛠️ 開發者設置指南 (Development Setup)

如果您想修改原始碼或在本地運行，請依照以下步驟：

1. **複製專案**：
   ```powershell
   git clone [https://github.com/FirePhoenix1001/DiscordMusicBot.git](https://github.com/FirePhoenix1001/DiscordMusicBot.git)
安裝依賴：

PowerShell
pip install -r requirements.txt
配置外部工具 (關鍵步驟)：
本專案依賴多個外部組件才能正常運作語音播放與 YouTube 解析。請在專案根目錄建立 tools/ 資料夾，並放入以下檔案：

FFmpeg：請下載 ffmpeg.exe 並放入 tools/。

Deno：請下載 deno.exe 並放入 tools/ (用於解析 YouTube 簽章)。

Opus DLL：請將 libopus-0.dll 放入 tools/ (Discord 語音壓縮核心)。

來源提示：可從 MSYS2 提取或使用專案提供的預編譯版本。

設定環境變數：
在根目錄建立 .env 檔案，並填入您的機器人 Token：

Plaintext
DISCORD_TOKEN=your_token_here
執行程式：

PowerShell
python src/main.py
📦 打包指令 (Build Executable)
若要將專案打包成單一 .exe 執行檔，請使用以下指令。此指令已包含強制收集語音加密庫 (PyNaCl) 與 Opus DLL 的配置：

PowerShell
pyinstaller --noconfirm --onefile --console --name "DiscordMusicBot" ^
--add-data "tools;tools" ^
--add-data "src;src" ^
--collect-all "nacl" ^
--collect-all "cffi" ^
--collect-binaries "discord" ^
--add-binary "tools/libopus-0.dll;tools" ^
.\src\main.py

---

### 🚀 接下來你可以：
1. **將檔案存為 `README.md`** 並放進 `C:\PythonProgram\DiscordMusicBot\`。
2. **執行 Git 指令**：
   ```powershell
   git add README.md
   git commit -m "文件：更新 README 說明文件"
   git push
