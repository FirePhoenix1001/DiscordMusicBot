@echo off
echo 正在清理舊的打包檔案...
rd /s /q build dist
echo 正在開始打包 DiscordMusicBot...
pyinstaller --noconfirm --onefile --console --name "DiscordMusicBot" ^
--add-data "tools;tools" ^
--add-data "src;src" ^
--collect-all "nacl" ^
--collect-all "cffi" ^
--collect-binaries "discord" ^
--add-binary "tools/libopus-0.dll;tools" ^
.\src\main.py
echo 打包完成！請查看 dist 資料夾。
pause