def format_url(url: str, start: str) -> str:
    if not url.startswith("http"):
        return f"{start}{url}"
    
    return url