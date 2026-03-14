#!/usr/bin/env python3
"""
钉钉推送签名测试脚本

用于验证钉钉加签算法是否正确实现
"""

import time
import hmac
import hashlib
import base64
from urllib.parse import quote_plus


def generate_dingtalk_sign(secret: str, timestamp: str = None) -> tuple[str, str]:
    """
    生成钉钉加签

    Args:
        secret: 加签密钥
        timestamp: 时间戳（毫秒），如不提供则使用当前时间

    Returns:
        (timestamp, sign) 元组
    """
    if timestamp is None:
        timestamp = str(round(time.time() * 1000))

    secret_enc = secret.encode('utf-8')
    string_to_sign = f'{timestamp}\n{secret}'
    string_to_sign_enc = string_to_sign.encode('utf-8')
    hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(hmac_code))

    return timestamp, sign


def build_dingtalk_url(access_token: str, secret: str = None) -> str:
    """
    构建钉钉 webhook URL

    Args:
        access_token: 访问令牌
        secret: 加签密钥（可选）

    Returns:
        完整的 webhook URL
    """
    base_url = f"https://oapi.dingtalk.com/robot/send?access_token={access_token}"

    if secret:
        timestamp, sign = generate_dingtalk_sign(secret)
        base_url = f"{base_url}&timestamp={timestamp}&sign={sign}"

    return base_url


if __name__ == "__main__":
    print("钉钉推送签名测试")
    print("=" * 60)

    # 测试用例
    test_secret = "SECtest1234567890abcdefghijklmnopqrstuvwxyz"
    test_timestamp = "1234567890000"

    timestamp, sign = generate_dingtalk_sign(test_secret, test_timestamp)

    print(f"密钥: {test_secret}")
    print(f"时间戳: {timestamp}")
    print(f"签名: {sign}")
    print()

    # 测试 URL 构建
    test_token = "test_access_token_123456"
    url_without_sign = build_dingtalk_url(test_token)
    url_with_sign = build_dingtalk_url(test_token, test_secret)

    print("不带签名的 URL:")
    print(url_without_sign)
    print()
    print("带签名的 URL:")
    print(url_with_sign)
    print()

    print("=" * 60)
    print("测试完成！")
    print()
    print("使用方法：")
    print("1. 在钉钉创建自定义机器人，选择「加签」安全设置")
    print("2. 复制 access_token 和 secret")
    print("3. 在 WebUI 中填写 webhook URL 和 secret")
    print("4. 系统会自动计算签名并添加到请求中")
