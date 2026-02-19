## 🛠️ 開發者設置指南 (Development Setup)

如果您想修改原始碼或在本地運行，請依照以下步驟：

1. **複製專案**：`git clone [https://github.com/FirePhoenix1001/DiscordMusicBot.git](https://github.com/FirePhoenix1001/DiscordMusicBot.git)`
2. **安裝依賴**：`pip install -r requirements.txt`
3. **配置 FFmpeg (關鍵步驟)**：
   * 本專案依賴多個外部組件才能正常運作語音播放與 YouTube 解析。請在專案根目錄建立 tools/ 資料夾，並放入以下檔案：
   * 請自行下載 `ffmpeg.exe` 及 `deno.exe` 及 `libopus-0.dll`。
   * 將它們放入專案根目錄中。
4. **執行程式**：`python src/main.py`
5. **打包指令**：`pyinstaller --noconfirm --onefile --console --name "DiscordMusicBot" --add-data "tools;tools" --add-data "src;src" --collect-all "nacl" --collect-all "cffi" --collect-binaries "discord" --add-binary "tools/libopus-0.dll;tools" .\src\main.py`
