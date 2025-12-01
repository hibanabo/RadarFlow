import requests

url = "https://www.dw.com/zh/%E5%9C%A8%E7%BA%BF%E6%8A%A5%E5%AF%BC/s-9058"

headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7",
    "Cache-Control": "no-cache",
    "Cookie": "pa_privacy=%22optin%22; _pc_c=fbb5a831-4406-3e6e-2675-0955b7bec81f; _pc_st=1764567592060; _pc_t=tracking_enabled; _pcid=%7B%22browserId%22%3A%22mimpzfxxyjo7gkbi%22%2C%22_t%22%3A%22myb4wxay%7Cmimpzfyy%22%7D; _pctx=%7Bu%7DN4IgrgzgpgThIC4B2YA2qA05owMoBcBDfSREQpAeyRCwgEt8oBJAE0RXSwH18yBbAJ4AjACwB3AB7CAjAB9%2B9fgAcAXgDNVMkAF8gA; __cmpconsentx70166=CQbvCQAQbvCQAAfCmEZHCHFgAP_gAEPgAAigI7JB9G5VaSFGODJzYLoAYAQXxlBJQgAgAACAAGAACBKAIAQEkEASIAgAIAAAABAAIBQAIQAoAAAAAACAAIAAAAAAAEAAAAAKAAAAAAAAQkAAAAAMAAAAEAAQAAAEAlAAgBAACBAAAIAAAQAAACAAAAAAAAAAAAAAAAAAQAAAQAAAQAAAAAAAAIAAAAAAAAAIEEdoFwACwAHQAUABUAC4AHAAPAAgABIACoAGQANAAcABMACqAF0APwAhIBEAESAI4ATQAnABWgDDAHOAO4AfoBCACLAEcAJMASkAz4B2wEXgJkATTAo8CkAFsALkAXMAvMBiwD5AIZgRvAjsAAA; __cmpcccx70166=aCQbw6WngA0Xgdf3rvDWMzWmmnrzSZDC4vCMmRotLgnoTAwjGqsDAJmVWjVgag1JjExU0mA1NRlFqtV5J4wSmDKAyiZJisBYAyoqJYRqIHSFeYBg; _pc_lr=1764567608295",
    "Pragma": "no-cache",
    "Priority": "u=0, i",
    "Sec-CH-UA": "\"Chromium\";v=\"142\", \"Google Chrome\";v=\"142\", \"Not_A Brand\";v=\"99\"",
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": "\"macOS\"",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
}

resp = requests.get(url, headers=headers, timeout=10)

print("Status:", resp.status_code)
print(resp.text[:500])  # 打印前500字符
