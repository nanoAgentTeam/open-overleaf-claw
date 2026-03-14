import os
import functools
from core.utils.logger import Logger
from core.infra.config import Config

# Lazy initialization: delay reading Config and constructing Langfuse until first use
langfuse = None
HAS_LANGFUSE = False
_initialized = False
_observe_impl = None


def _noop_observe(*args, **kwargs):
    """Fallback decorator when Langfuse is unavailable."""
    if len(args) == 1 and callable(args[0]):
        return args[0]
    def decorator(func):
        return func
    return decorator


def _ensure_langfuse():
    """Initialize Langfuse once; safe to call multiple times."""
    global _initialized, HAS_LANGFUSE, langfuse, _observe_impl
    if _initialized:
        return
    _initialized = True
    
    # 强制禁用开关 (不再打印 Log)
    if not Config.LANGFUSE_ENABLED or os.environ.get("DISABLE_LANGFUSE", "").lower() == "true":
        HAS_LANGFUSE = False
        langfuse = None
        _observe_impl = _noop_observe
        return

    try:
        # Import only when needed and not disabled
        from langfuse import Langfuse, observe as lf_observe
    except ImportError:
        HAS_LANGFUSE = False
        langfuse = None
        _observe_impl = _noop_observe
        return

    # 优先从 Config 读取 Langfuse 配置，缺省时再回退到环境变量
    public_key = Config.LANGFUSE_PUBLIC_KEY or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = Config.LANGFUSE_SECRET_KEY or os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = Config.LANGFUSE_HOST or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if public_key and secret_key:
        langfuse = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        HAS_LANGFUSE = True
        _observe_impl = lf_observe
    else:
        HAS_LANGFUSE = False
        langfuse = None
        _observe_impl = _noop_observe


def observe(*args, **kwargs):
    """
    真正意义上的懒加载装饰器。
    在模块导入和装饰函数时不会触发任何初始化动作。
    只有当被装饰的函数第一次被调用时，才会读取 Config 并初始化 Langfuse。
    """
    # 判断是 @observe 还是 @observe(...)
    is_direct = len(args) == 1 and callable(args[0])
    
    def decorator(func):
        # 这里的代码在函数定义时执行，不触发初始化
        real_wrapped_func = None

        @functools.wraps(func)
        def wrapper(*f_args, **f_kwargs):
            nonlocal real_wrapped_func
            # 只有在第一次运行时执行初始化和包装逻辑
            if real_wrapped_func is None:
                _ensure_langfuse()
                # 此时 _observe_impl 已经根据运行时 Config 确定是真 observe 还是 no-op
                try:
                    if is_direct:
                        real_wrapped_func = _observe_impl(func)
                    else:
                        real_wrapped_func = _observe_impl(*args, **kwargs)(func)
                except Exception as e:
                    print(f"[Langfuse] Failed to wrap with observe: {e}")
                    real_wrapped_func = func

            # 执行被装饰后的函数，并捕获可能的 Langfuse 运行时异常
            try:
                result = real_wrapped_func(*f_args, **f_kwargs)
                
                # 如果返回的是生成器，需要包装生成器以捕获迭代过程中的超时
                import inspect
                if inspect.isgenerator(result):
                    def safe_generator(gen):
                        try:
                            for item in gen:
                                yield item
                        except Exception as ge:
                            ge_str = str(ge).lower()
                            if "timeout" in ge_str or "langfuse" in ge_str:
                                print(f"[Langfuse Generator Error] {ge}. Continuing without trace.")
                            else:
                                raise ge
                    return safe_generator(result)
                
                return result
            except Exception as e:
                # 如果是网络超时或 Langfuse 相关错误，尝试降级运行原始函数
                error_str = str(e).lower()
                if "langfuse" in error_str or "timeout" in error_str or "connection" in error_str:
                    print(f"[Langfuse Runtime Error] {e}. Falling back to original function to avoid task failure.")
                    # 注意：如果此时函数已经执行了一部分，重新执行可能会有副作用
                    # 但对于评估系统来说，确保任务跑完比 Trace 丢失更重要
                    return func(*f_args, **f_kwargs)
                raise e
        return wrapper

    if is_direct:
        return decorator(args[0])
    return decorator
