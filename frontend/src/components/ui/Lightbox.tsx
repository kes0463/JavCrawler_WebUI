import { useEffect } from "react";
import { X } from "lucide-react";

interface LightboxProps {
  src: string;
  onClose: () => void;
}

export function Lightbox({ src, onClose }: LightboxProps) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      data-lightbox
      className="fixed inset-0 z-[100] bg-black/90 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button
        type="button"
        className="absolute top-4 right-4 p-2 rounded-full bg-white/10 hover:bg-white/20"
        onClick={onClose}
        aria-label="닫기"
      >
        <X className="w-6 h-6" />
      </button>
      <img
        src={src}
        alt=""
        className="max-w-full max-h-[90vh] object-contain"
        onClick={e => e.stopPropagation()}
      />
    </div>
  );
}
