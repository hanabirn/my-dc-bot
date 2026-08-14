# addImage.py
import re
import os

TARGET_FILE = "googleSearch.py"

def add_url_to_pool():
    if not os.path.exists(TARGET_FILE):
        print(f"❌ 找不到 {TARGET_FILE}，請確認檔案是否存在於當前目錄下！")
        return

    print("🎤 歡迎使用 Miku 卡池自動加圖工具 (重複自動重試版) ♪")
    print("-" * 50)

    # 🔄 使用迴圈讓你可以一直重複加圖
    while True:
        url = input("\n👉 請貼上你想新增的圖片網址 (或直接按 Enter 取消)：").strip()

        # 如果使用者直接按 Enter 沒有輸入東西，就問他要不要繼續
        if not url:
            print("💡 未偵測到輸入網址。")
        else:
            # 簡單防呆：網址必須以 http 或 https 開頭
            if not (url.startswith("http://") or url.startswith("https://")):
                print("❌ 這似乎不是一個有效的網址（必須以 http:// 或 https:// 開頭）！")
            else:
                # 讀取原本的檔案內容
                with open(TARGET_FILE, "r", encoding="utf-8") as f:
                    content = f.read()

                # 使用正則表達式尋找 BEAUTY_IMAGES = [ ... ] 的區塊
                pattern = r"(BEAUTY_IMAGES\s*=\s*\[)(.*?)(\s*\])"
                match = re.search(pattern, content, re.DOTALL)

                if not match:
                    print(f"❌ 在 {TARGET_FILE} 中找不到 BEAUTY_IMAGES 陣列格式！")
                    break

                prefix = match.group(1)   # "BEAUTY_IMAGES = ["
                inner_content = match.group(2) # 陣列內原本的圖片網址們
                suffix = match.group(3)   # "]"

                # 🔍 檢查網址是否已經在裡面了
                if f"'{url}'" in inner_content or f'"{url}"' in inner_content:
                    print("⚠️ 警告：這張圖片網址已經重複過囉！請改上傳另一個圖片網址。")
                    print("-" * 40)
                    # 🎯 關鍵改動：使用 continue 直接跳過後面的詢問，立馬讓使用者重新輸入網址！
                    continue 

                # 整理格式並寫入檔案
                cleaned_inner = inner_content.strip()
                if cleaned_inner == "":
                    new_inner = f"\n    '{url}',\n"
                else:
                    if not cleaned_inner.endswith(","):
                        cleaned_inner += ","
                    new_inner = f"\n    {cleaned_inner}\n    '{url}',\n"

                # 組合成新的檔案內容並寫回
                new_block = f"{prefix}{new_inner}{suffix}"
                updated_content = content.replace(match.group(0), new_block)

                with open(TARGET_FILE, "w", encoding="utf-8") as f:
                    f.write(updated_content)

                print("💚 成功！已將新美圖自動存入大圖庫囉！(39♪)")

        # ❓ 只有在成功加入圖片或按了空白時，才會詢問是否要繼續
        print("-" * 40)
        choice = input("🎤 是否還要再加入新的圖片？(Yes / no)：").strip().lower()
        print("-" * 40)

        # 如果輸入的是 no、n 或者不想加了，就跳出迴圈結束程式
        if choice in ['no', 'n']:
            print("🎤 謝謝使用！Miku 已經把新卡片都收好囉，記得重啟 Bot 喔！掰掰♪")
            break

if __name__ == "__main__":
    add_url_to_pool()