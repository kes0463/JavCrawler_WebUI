import { ImageLightbox } from "@/components/library/ImageLightbox";

interface CoverLightboxProps {
  open: boolean;
  src: string;
  alt: string;
  onClose: () => void;
}

export function CoverLightbox({ open, src, alt, onClose }: CoverLightboxProps) {
  return (
    <ImageLightbox
      open={open}
      src={src}
      alt={alt}
      onClose={onClose}
      zIndex={60}
      ariaLabel="표지 확대"
    />
  );
}
