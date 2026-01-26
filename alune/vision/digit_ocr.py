from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

_MODEL_PATH = Path(__file__).parent / "models" / "paddle_rec" / "model.onnx"
_DICT_PATH = Path(__file__).parent / "models" / "paddle_rec" / "dict.txt"


class DigitOCR:
    """
    PaddleOCR recognition (rec) ONNX wrapper.
    Reads the whole ROI as a text line (no contour splitting).
    CTC decode using dict.txt and then filters to digits only.
    """

    def __init__(self, min_text_conf: float = 0.0):
        # Start permissive; tighten later once you see stable outputs.
        self.min_text_conf = float(min_text_conf)

        self.session = ort.InferenceSession(
            str(_MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

        # Many PaddleOCR rec exports use dynamic width; standard deploy uses H=32, W=320.
        self.in_h = 32
        self.in_w = 320

        self.charset = self._load_charset(_DICT_PATH)

    def get_number_from_image(self, roi: np.ndarray, max_digits: int = 2) -> int | None:
        text, conf = self._recognize_text(roi)
        if text is None or conf < self.min_text_conf:
            return None

        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return None

        if len(digits) > max_digits:
            digits = digits[-max_digits:]

        try:
            return int(digits)
        except ValueError:
            return None

    # -------- internals --------

    def _load_charset(self, path: Path) -> list[str]:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [ln.strip("\ufeff") for ln in lines if ln.strip() != ""]

    def _recognize_text(self, roi: np.ndarray) -> tuple[str | None, float]:
        if roi is None or roi.size == 0:
            return None, 0.0

        x = self._preprocess(roi)  # (1,3,32,320)

        outs = self.session.run(None, {self.input_name: x})
        logits = outs[0]  # expected (N, T, C)

        if logits is None or len(logits.shape) != 3:
            return None, 0.0

        probs = self._softmax(logits, axis=2)[0]  # (T, C)
        pred_ids = np.argmax(probs, axis=1)  # (T,)
        pred_confs = np.max(probs, axis=1)  # (T,)

        text, conf = self._ctc_decode(pred_ids, pred_confs)
        return text, conf

    def _preprocess(self, roi: np.ndarray) -> np.ndarray:
        """
        PaddleOCR rec preprocessing (BGR-based, OpenCV-style):
        - ensure 3-channel BGR
        - resize to height 32 keeping aspect, pad right to width 320
        - normalize to [-1,1] using (x/255 - 0.5)/0.5
        - output NCHW float32
        """
        img = roi

        # Ensure 3-channel BGR
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.ndim == 3 and img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        h, w = img.shape[:2]

        # Resize to target height keeping aspect ratio
        scale = self.in_h / float(h)
        new_w = int(round(w * scale))
        new_w = max(1, min(new_w, self.in_w))

        img = cv2.resize(img, (new_w, self.in_h), interpolation=cv2.INTER_CUBIC)

        # Pad to (32, 320)
        padded = np.zeros((self.in_h, self.in_w, 3), dtype=np.uint8)
        padded[:, :new_w, :] = img

        x = padded.astype(np.float32) / 255.0
        x = (x - 0.5) / 0.5  # [-1, 1]

        # HWC -> CHW -> NCHW
        x = np.transpose(x, (2, 0, 1))
        x = np.expand_dims(x, axis=0)
        return x.astype(np.float32)

    def _ctc_decode(self, ids: np.ndarray, confs: np.ndarray) -> tuple[str, float]:
        """
        CTC decode:
        - remove repeats
        - remove blanks (id=0)
        Map id -> charset[id-1]
        """
        last = -1
        out_chars: list[str] = []
        out_confs: list[float] = []

        for cid, cconf in zip(ids.tolist(), confs.tolist()):
            if cid == last:
                continue
            last = cid
            if cid == 0:
                continue  # blank

            idx = cid - 1
            if 0 <= idx < len(self.charset):
                out_chars.append(self.charset[idx])
                out_confs.append(float(cconf))

        text = "".join(out_chars)
        mean_conf = float(sum(out_confs) / len(out_confs)) if out_confs else 0.0
        return text, mean_conf

    def _softmax(self, x: np.ndarray, axis: int = -1) -> np.ndarray:
        x = x.astype(np.float32)
        x = x - np.max(x, axis=axis, keepdims=True)
        e = np.exp(x)
        return e / np.sum(e, axis=axis, keepdims=True)
