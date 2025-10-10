"""
翻译模块 - 支持腾讯翻译、百度翻译、谷歌翻译
"""
import asyncio
import aiohttp
import json
import hashlib
import hmac
import time
import random
from datetime import datetime
from urllib.parse import quote
from astrbot.api import logger

# 腾讯云SDK导入
try:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
    from tencentcloud.tmt.v20180321 import tmt_client, models
    TENCENT_SDK_AVAILABLE = True
except ImportError:
    TENCENT_SDK_AVAILABLE = False
    logger.warning("腾讯云SDK未安装，将使用自定义实现")


class TranslationError(Exception):
    """翻译错误异常"""
    pass


class BaseTranslator:
    """翻译器基类"""
    
    def __init__(self, config: dict):
        self.config = config
    
    async def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        """翻译文本"""
        raise NotImplementedError
    
    def _should_translate(self, text: str) -> bool:
        """判断是否需要翻译"""
        if not text or not text.strip():
            return False
        
        # 检查长度阈值
        threshold = self.config.get("translate_threshold", 10)
        if len(text.strip()) < threshold:
            return False
        
        return True


class TencentTranslator(BaseTranslator):
    """腾讯云翻译"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.secret_id = config.get("tencent_secret_id", "")
        self.secret_key = config.get("tencent_secret_key", "")
        self.endpoint = "tmt.tencentcloudapi.com"
        
        if not self.secret_id or not self.secret_key:
            raise TranslationError("腾讯翻译API配置不完整：缺少SecretId或SecretKey")
    
    def _sign(self, secret_key: str, string_to_sign: str) -> str:
        """生成签名"""
        return hmac.new(
            secret_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_authorization(self, payload: str, timestamp: int) -> str:
        """生成授权头"""
        # 步骤1：拼接规范请求串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{self.endpoint}\nx-tc-action:TextTranslate\nx-tc-timestamp:{timestamp}\nx-tc-version:2018-03-21\n"
        signed_headers = "content-type;host;x-tc-action;x-tc-timestamp;x-tc-version"
        hashed_request_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        canonical_request = f"{http_request_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_request_payload}"
        
        # 步骤2：拼接待签名字符串
        algorithm = "TC3-HMAC-SHA256"
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        service = "tmt"
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}"
        
        # 步骤3：计算签名
        secret_date = hmac.new(f"TC3{self.secret_key}".encode('utf-8'), date.encode('utf-8'), hashlib.sha256).digest()
        secret_service = hmac.new(secret_date, service.encode('utf-8'), hashlib.sha256).digest()
        secret_signing = hmac.new(secret_service, "tc3_request".encode('utf-8'), hashlib.sha256).digest()
        signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # 步骤4：拼接Authorization
        authorization = f"{algorithm} Credential={self.secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        return authorization
    
    async def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        """使用腾讯云翻译API翻译文本"""
        if not self._should_translate(text):
            return text
        
        # 优先使用官方SDK
        if TENCENT_SDK_AVAILABLE:
            return await self._translate_with_sdk(text, source_lang, target_lang)
        else:
            return await self._translate_with_custom(text, source_lang, target_lang)
    
    async def _translate_with_sdk(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        """使用腾讯云官方SDK翻译"""
        try:
            # 语言代码映射
            lang_map = {
                "auto": "auto",
                "zh": "zh",
                "en": "en",
                "ja": "ja",
                "ko": "ko",
                "fr": "fr",
                "de": "de",
                "es": "es",
                "ru": "ru"
            }
            
            source = lang_map.get(source_lang, source_lang)
            target = lang_map.get(target_lang, target_lang)
            
            # 创建认证对象
            cred = credential.Credential(self.secret_id, self.secret_key)
            
            # 实例化一个http选项，可选的，没有特殊需求可以跳过
            httpProfile = HttpProfile()
            httpProfile.endpoint = self.endpoint
            
            # 实例化一个client选项，可选的，没有特殊需求可以跳过
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile
            
            # 实例化要请求产品的client对象，clientProfile是可选的
            client = tmt_client.TmtClient(cred, "ap-beijing", clientProfile)
            
            # 实例化一个请求对象，每个接口都会对应一个request对象
            req = models.TextTranslateRequest()
            req.SourceText = text
            req.Source = source
            req.Target = target
            req.ProjectId = 0
            
            # 返回的resp是一个TextTranslateResponse的实例，与请求对象对应
            resp = client.TextTranslate(req)
            
            translated_text = resp.TargetText
            logger.info(f"🌐 腾讯翻译成功(SDK): '{text[:50]}...' -> '{translated_text[:50]}...'")
            return translated_text
            
        except TencentCloudSDKException as e:
            logger.error(f"❌ 腾讯翻译SDK失败: {e}")
            return text
        except Exception as e:
            logger.error(f"❌ 腾讯翻译SDK异常: {e}")
            return text
    
    async def _translate_with_custom(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        """使用自定义实现翻译"""
        if not self._should_translate(text):
            return text
        
        try:
            # 语言代码映射
            lang_map = {
                "auto": "auto",
                "zh": "zh",
                "en": "en",
                "ja": "ja",
                "ko": "ko",
                "fr": "fr",
                "de": "de",
                "es": "es",
                "ru": "ru"
            }
            
            source = lang_map.get(source_lang, source_lang)
            target = lang_map.get(target_lang, target_lang)
            
            # 构建请求参数
            timestamp = int(time.time())
            payload = json.dumps({
                "Action": "TextTranslate",
                "Version": "2018-03-21",
                "SourceText": text,
                "Source": source,
                "Target": target,
                "ProjectId": 0
            })
            
            # 生成授权头
            authorization = self._get_authorization(payload, timestamp)
            
            headers = {
                "Authorization": authorization,
                "Content-Type": "application/json; charset=utf-8",
                "Host": self.endpoint,
                "X-TC-Action": "TextTranslate",
                "X-TC-Timestamp": str(timestamp),
                "X-TC-Version": "2018-03-21"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://{self.endpoint}",
                    headers=headers,
                    data=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    result = await response.json()
                    logger.info(f"🔍 腾讯翻译API响应: {result}")
                    
                    if response.status != 200:
                        raise TranslationError(f"腾讯翻译API请求失败: {response.status}")
                    
                    if "Error" in result:
                        error_msg = result["Error"].get("Message", "未知错误")
                        raise TranslationError(f"腾讯翻译API错误: {error_msg}")
                    
                    # 检查响应结构
                    if "Response" not in result:
                        raise TranslationError(f"腾讯翻译API响应格式错误: 缺少Response字段")
                    
                    if "TargetText" not in result["Response"]:
                        raise TranslationError(f"腾讯翻译API响应格式错误: 缺少TargetText字段")
                    
                    translated_text = result["Response"]["TargetText"]
                    logger.info(f"🌐 腾讯翻译成功: '{text[:50]}...' -> '{translated_text[:50]}...'")
                    return translated_text
                    
        except Exception as e:
            logger.error(f"❌ 腾讯翻译失败: {e}")
            return text  # 翻译失败时返回原文


class BaiduTranslator(BaseTranslator):
    """百度翻译"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.app_id = config.get("baidu_app_id", "")
        self.secret_key = config.get("baidu_secret_key", "")
        self.endpoint = "https://fanyi-api.baidu.com/api/trans/vip/translate"
        
        if not self.app_id or not self.secret_key:
            raise TranslationError("百度翻译API配置不完整：缺少APP ID或密钥")
    
    def _generate_sign(self, query: str, salt: str) -> str:
        """生成签名"""
        sign_str = f"{self.app_id}{query}{salt}{self.secret_key}"
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest()
    
    async def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        """使用百度翻译API翻译文本"""
        if not self._should_translate(text):
            return text
        
        try:
            # 语言代码映射
            lang_map = {
                "auto": "auto",
                "zh": "zh",
                "en": "en",
                "ja": "jp",
                "ko": "kor",
                "fr": "fra",
                "de": "de",
                "es": "spa",
                "ru": "ru"
            }
            
            source = lang_map.get(source_lang, source_lang)
            target = lang_map.get(target_lang, target_lang)
            
            # 生成随机数
            salt = str(random.randint(32768, 65536))
            
            # 生成签名
            sign = self._generate_sign(text, salt)
            
            # 构建请求参数
            params = {
                "q": text,
                "from": source,
                "to": target,
                "appid": self.app_id,
                "salt": salt,
                "sign": sign
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint,
                    data=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    result = await response.json()
                    
                    if response.status != 200:
                        raise TranslationError(f"百度翻译API请求失败: {response.status}")
                    
                    if "error_code" in result:
                        error_msg = result.get("error_msg", "未知错误")
                        raise TranslationError(f"百度翻译API错误: {error_msg}")
                    
                    if "trans_result" not in result or not result["trans_result"]:
                        raise TranslationError("百度翻译API返回结果为空")
                    
                    translated_text = result["trans_result"][0]["dst"]
                    logger.info(f"🌐 百度翻译成功: '{text[:50]}...' -> '{translated_text[:50]}...'")
                    return translated_text
                    
        except Exception as e:
            logger.error(f"❌ 百度翻译失败: {e}")
            return text  # 翻译失败时返回原文


class GoogleTranslator(BaseTranslator):
    """谷歌翻译"""
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("google_api_key", "")
        self.endpoint = "https://translation.googleapis.com/language/translate/v2"
        
        if not self.api_key:
            raise TranslationError("谷歌翻译API配置不完整：缺少API密钥")
    
    async def translate(self, text: str, source_lang: str = "auto", target_lang: str = "zh") -> str:
        """使用谷歌翻译API翻译文本"""
        if not self._should_translate(text):
            return text
        
        try:
            # 语言代码映射
            lang_map = {
                "auto": "",  # 谷歌翻译自动检测不需要指定源语言
                "zh": "zh-cn",
                "en": "en",
                "ja": "ja",
                "ko": "ko",
                "fr": "fr",
                "de": "de",
                "es": "es",
                "ru": "ru"
            }
            
            target = lang_map.get(target_lang, target_lang)
            
            # 构建请求参数
            params = {
                "key": self.api_key,
                "q": text,
                "target": target,
                "format": "text"
            }
            
            # 如果不是自动检测，添加源语言
            if source_lang != "auto":
                source = lang_map.get(source_lang, source_lang)
                if source:
                    params["source"] = source
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint,
                    data=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    result = await response.json()
                    
                    if response.status != 200:
                        raise TranslationError(f"谷歌翻译API请求失败: {response.status}")
                    
                    if "error" in result:
                        error_msg = result["error"].get("message", "未知错误")
                        raise TranslationError(f"谷歌翻译API错误: {error_msg}")
                    
                    if "data" not in result or "translations" not in result["data"]:
                        raise TranslationError("谷歌翻译API返回结果格式错误")
                    
                    translations = result["data"]["translations"]
                    if not translations:
                        raise TranslationError("谷歌翻译API返回结果为空")
                    
                    translated_text = translations[0]["translatedText"]
                    logger.info(f"🌐 谷歌翻译成功: '{text[:50]}...' -> '{translated_text[:50]}...'")
                    return translated_text
                    
        except Exception as e:
            logger.error(f"❌ 谷歌翻译失败: {e}")
            return text  # 翻译失败时返回原文


class TranslatorManager:
    """翻译管理器"""
    
    def __init__(self, config: dict):
        self.config = config
        self.translator = None
        self._init_translator()
    
    def _init_translator(self):
        """初始化翻译器"""
        if not self.config.get("enable_translation", False):
            logger.info("🌐 翻译功能已禁用")
            return
        
        provider = self.config.get("translation_provider", "tencent")
        
        try:
            if provider == "tencent":
                self.translator = TencentTranslator(self.config)
                logger.info("🌐 腾讯翻译器初始化成功")
            elif provider == "baidu":
                self.translator = BaiduTranslator(self.config)
                logger.info("🌐 百度翻译器初始化成功")
            elif provider == "google":
                self.translator = GoogleTranslator(self.config)
                logger.info("🌐 谷歌翻译器初始化成功")
            else:
                logger.warning(f"⚠️ 不支持的翻译提供商: {provider}")
                
        except TranslationError as e:
            logger.error(f"❌ 翻译器初始化失败: {e}")
            self.translator = None
        except Exception as e:
            logger.error(f"❌ 翻译器初始化异常: {e}")
            self.translator = None
    
    def update_config(self, config: dict):
        """更新配置并重新初始化翻译器"""
        self.config = config
        self._init_translator()
    
    async def translate(self, text: str) -> str:
        """翻译文本"""
        if not self.translator:
            return text
        
        if not self.config.get("enable_translation", False):
            return text
        
        source_lang = self.config.get("source_language", "auto")
        target_lang = self.config.get("target_language", "zh")
        
        try:
            return await self.translator.translate(text, source_lang, target_lang)
        except Exception as e:
            logger.error(f"❌ 翻译过程中发生异常: {e}")
            return text
    
    def is_enabled(self) -> bool:
        """检查翻译功能是否启用"""
        return self.config.get("enable_translation", False) and self.translator is not None