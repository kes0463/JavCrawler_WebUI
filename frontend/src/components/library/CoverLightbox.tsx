import { ImageLightbox } from "@/components/library/ImageLightbox";

/** LibraryDetailPanel(z-110) 위에 표시 */
const COVER_LIGHTBOX_Z = 115;

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
      zIndex={COVER_LIGHTBOX_Z}
      ariaLabel="표지 확대"
    />
  );
}
