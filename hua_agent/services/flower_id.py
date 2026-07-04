"""External flower identification service client."""

import json as _json
import logging
import urllib.error as _url_error
import urllib.request as _req

from fastapi import HTTPException

_logger = logging.getLogger(__name__)


def identify_flower_from_url(image_url: str) -> str:
    """Identify flower name from an image URL via external API."""
    body = _json.dumps({"image_url": image_url}).encode()
    rq = _req.Request(
        "http://127.0.0.1:8000/predict",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _req.urlopen(rq, timeout=30) as resp:
            data = _json.loads(resp.read())
        return data["data"]["flower_name"]
    except _url_error.URLError:
        _logger.exception("外部花卉识别接口网络故障")
        raise HTTPException(status_code=502, detail="外部花卉识别接口网络不可达")
    except (KeyError, _json.JSONDecodeError):
        _logger.exception("外部花卉识别接口返回格式异常")
        raise HTTPException(status_code=500, detail="外部花卉识别接口返回格式异常")
    except Exception:
        _logger.exception("外部花卉识别接口未知错误")
        raise HTTPException(status_code=500, detail="外部花卉识别接口暂不可用")
