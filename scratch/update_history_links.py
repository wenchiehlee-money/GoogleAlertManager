import re
from pathlib import Path

def update_links_in_file(file_path: Path):
    content = file_path.read_text(encoding="utf-8")
    
    # 匹配修正連結中的第 5 分，並提取 title params 以及 body params
    # 格式：[5](https://github.com/wenchiehlee-money/GoogleAlertManager/issues/new?title=... 5&body=Change+rating+to+5+for+AI+learning. Reason%3A+)
    pattern = r'(\[5\]\((https://github\.com/[^/]+/[^/]+/issues/new\?title=.+?)\+5(&body=Change\+rating\+to\+)5(\+for\+AI\+learning\..*?)\))'
    
    def replace_func(match):
        full_5 = match.group(1)
        base_url_with_title = match.group(2)
        body_prefix = match.group(3)
        body_suffix = match.group(4)
        
        # 構造 6 的連結
        link_6 = f" / [6]({base_url_with_title}+6{body_prefix}6{body_suffix})"
        
        # 檢查是否已經有 6 分連結，避免重複添加
        if " / [6]" in content[match.end():match.end()+100]:
            return full_5
            
        return full_5 + link_6

    # 執行替換
    new_content = re.sub(pattern, replace_func, content)
    if new_content != content:
        file_path.write_text(new_content, encoding="utf-8")
        print(f"Updated file: {file_path}")
        return True
    return False

def main():
    reports_dir = Path(__file__).parent.parent / "data" / "reports"
    if not reports_dir.exists():
        print("找不到 data/reports 目錄。")
        return
        
    count = 0
    # 遞迴尋找所有個股 md 檔案 (排除 summary.md)
    for md_file in reports_dir.rglob("*.md"):
        if md_file.name.endswith("-summary.md") or md_file.name == "bookmarks.md":
            continue
        if update_links_in_file(md_file):
            count += 1
            
    print(f"Done! Updated {count} files.")

if __name__ == "__main__":
    main()
