import { useRef, useState } from "react";
import { Upload, User, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import { Lightbox } from "@/components/ui/Lightbox";
import {
  actressPhotoUrl,
  setActressProfileImage,
  uploadActressImage,
  type ActressGalleryImage,
  type ActressProfile,
} from "@/api/actress";

interface ActressGalleryProps {
  profile: ActressProfile;
  onProfileChange: (profile: ActressProfile) => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
}

export function ActressGallery({
  profile,
  onProfileChange,
  onError,
  onSuccess,
}: ActressGalleryProps) {
  const profileInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState<"profile" | "gallery" | null>(null);

  const pickImageFiles = (fileList: FileList | null): File[] => {
    if (!fileList?.length) return [];
    return Array.from(fileList).filter(f => f.type.startsWith("image/"));
  };

  const uploadFiles = async (files: File[], isProfile: boolean) => {
    const images = files.filter(f => f.type.startsWith("image/"));
    if (images.length === 0) return;

    const queue = isProfile ? images.slice(0, 1) : images;
    setUploading(true);
    let succeeded = 0;
    let failed = 0;
    let lastError = "";

    try {
      for (const file of queue) {
        try {
          const res = await uploadActressImage(profile.id, file, isProfile);
          onProfileChange(res.profile);
          succeeded += 1;
        } catch (err) {
          failed += 1;
          lastError = String((err as Error).message || err);
          if (isProfile) throw err;
        }
      }

      if (isProfile) {
        onSuccess("대표 사진이 업데이트되었습니다.");
      } else if (failed === 0) {
        onSuccess(
          succeeded === 1
            ? "갤러리에 사진이 추가되었습니다."
            : `갤러리에 사진 ${succeeded}장이 추가되었습니다.`,
        );
      } else if (succeeded > 0) {
        onSuccess(`갤러리 ${succeeded}장 추가 · ${failed}장 실패`);
      } else {
        onError(lastError || "사진 업로드에 실패했습니다.");
      }
    } catch (err) {
      onError(String((err as Error).message || err));
    } finally {
      setUploading(false);
    }
  };

  const handleFileInput = async (
    e: React.ChangeEvent<HTMLInputElement>,
    isProfile: boolean,
  ) => {
    const files = pickImageFiles(e.target.files);
    e.target.value = "";
    if (files.length === 0) return;
    await uploadFiles(files, isProfile);
  };

  const handleDrop = async (e: React.DragEvent, isProfile: boolean) => {
    e.preventDefault();
    setDragOver(null);
    const files = pickImageFiles(e.dataTransfer.files);
    if (files.length === 0) return;
    await uploadFiles(files, isProfile);
  };

  const promoteToProfile = async (img: ActressGalleryImage) => {
    if (!img.image_id) {
      onError("이미지 ID가 없어 대표 사진으로 설정할 수 없습니다.");
      return;
    }
    try {
      const res = await setActressProfileImage(profile.id, img.image_id);
      onProfileChange(res.profile);
      onSuccess("대표 사진으로 설정했습니다.");
    } catch (err) {
      onError(String((err as Error).message || err));
    }
  };

  const gallery = profile.gallery_images ?? [];

  return (
    <>
      <div className="flex flex-col sm:flex-row gap-4 items-stretch w-full">
        {/* 대표 사진 */}
        <div className="shrink-0 w-full sm:w-56 lg:w-64 xl:w-72">
          <div
            className={cn(
              "aspect-[3/4] rounded-xl overflow-hidden bg-[#0a0a12] border relative cursor-pointer group",
              dragOver === "profile"
                ? "border-violet-500/60 bg-violet-500/10"
                : "border-white/[0.08]",
            )}
            onClick={() => {
              if (profile.profile_image_url) {
                setLightboxUrl(actressPhotoUrl(profile.profile_image_url));
              } else {
                profileInputRef.current?.click();
              }
            }}
            onDragOver={e => { e.preventDefault(); setDragOver("profile"); }}
            onDragLeave={() => setDragOver(null)}
            onDrop={e => handleDrop(e, true)}
          >
            {profile.profile_image_url ? (
              <img
                src={actressPhotoUrl(profile.profile_image_url)}
                alt=""
                draggable={false}
                className="w-full h-full object-contain object-top bg-black/40 pointer-events-none"
              />
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center text-slate-500 gap-2">
                <User className="w-14 h-14" />
                <span className="text-xs text-center px-2">대표 사진 없음<br />(클릭 또는 드래그)</span>
              </div>
            )}
            <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <p className="text-[11px] text-white font-medium">클릭 → 크게 보기</p>
            </div>
          </div>
          <input
            ref={profileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={e => handleFileInput(e, true)}
          />
          <button
            type="button"
            disabled={uploading}
            onClick={() => profileInputRef.current?.click()}
            className="mt-2 w-full flex items-center justify-center gap-1 py-2 text-sm rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] hover:text-white transition-colors disabled:opacity-50"
          >
            <Upload className="w-4 h-4" /> 대표 사진
          </button>
        </div>

        {/* 갤러리 — 남는 너비·높이 최대 활용 */}
        <div className="flex-1 min-w-0 flex flex-col">
          <p className="text-sm text-slate-400 mb-2 shrink-0">
            갤러리 ({gallery.length})
          </p>
          <div
            className={cn(
              "flex-1 rounded-xl border p-3 min-h-[220px] sm:min-h-[300px] lg:min-h-[340px]",
              dragOver === "gallery"
                ? "border-violet-500/60 bg-violet-500/10"
                : "border-white/[0.08] bg-black/20",
            )}
            onDragOver={e => { e.preventDefault(); setDragOver("gallery"); }}
            onDragLeave={() => setDragOver(null)}
            onDrop={e => handleDrop(e, false)}
          >
            {gallery.length === 0 ? (
              <p className="text-sm text-slate-500 text-center py-12">
                갤러리 사진 없음<br />
                <span className="text-xs text-slate-600">여러 장을 한 번에 드래그할 수 있습니다</span>
              </p>
            ) : (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(88px,1fr))] sm:grid-cols-[repeat(auto-fill,minmax(100px,1fr))] lg:grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-2.5 w-full">
                {gallery.map((img, idx) => (
                  <div
                    key={img.image_id ?? img.image_url ?? idx}
                    className="relative group"
                  >
                    <button
                      type="button"
                      className="flex items-center justify-center w-full aspect-[3/4] rounded-lg border border-white/10 bg-black/30 hover:border-violet-500/40 p-1 transition-colors"
                      onClick={() => setLightboxUrl(actressPhotoUrl(img.image_url || img.thumb_url))}
                    >
                      <img
                        src={actressPhotoUrl(img.thumb_url || img.image_url)}
                        alt=""
                        draggable={false}
                        className="max-w-full max-h-full w-auto h-auto object-contain pointer-events-none"
                      />
                    </button>
                    {img.image_id && (
                      <button
                        type="button"
                        title="대표 사진으로 설정"
                        onClick={() => promoteToProfile(img)}
                        className="absolute top-1.5 right-1.5 p-1 rounded bg-black/70 text-amber-300 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Star className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
          <input
            ref={galleryInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={e => handleFileInput(e, false)}
          />
          <button
            type="button"
            disabled={uploading}
            onClick={() => galleryInputRef.current?.click()}
            className="mt-2 w-full flex items-center justify-center gap-1 py-2 text-sm rounded-xl bg-bg-surface border border-white/[0.08] text-[#c8c8e0] hover:text-white transition-colors disabled:opacity-50"
          >
            <Upload className="w-4 h-4" /> 갤러리 추가
          </button>
        </div>
      </div>

      {lightboxUrl && (
        <Lightbox src={lightboxUrl} onClose={() => setLightboxUrl(null)} />
      )}
    </>
  );
}
