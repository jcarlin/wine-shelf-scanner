'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Camera, Upload, Wine } from 'lucide-react';
import { colors } from '@/lib/theme';

interface CameraCaptureProps {
  onImageSelected: (file: File) => void;
  isLoading?: boolean;
}

export function CameraCapture({ onImageSelected, isLoading }: CameraCaptureProps) {
  const t = useTranslations('camera');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onImageSelected(file);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      onImageSelected(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const openCamera = () => {
    cameraInputRef.current?.click();
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-6">
      {/* Hero Section */}
      <div className="text-center mb-12">
        <div
          className="w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-6"
          style={{ backgroundColor: colors.wine }}
        >
          <Wine className="w-12 h-12 text-white" />
        </div>
        <h1 className="text-3xl font-bold text-white mb-3">
          {t('heroTitle')}
        </h1>
        <p className="text-gray-400 text-lg max-w-md">
          {t('heroSubtitle')}
        </p>
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`
          w-full max-w-md p-8 rounded-xl border-2 border-dashed
          transition-all duration-200 cursor-pointer mb-6
          ${isDragOver
            ? 'border-star bg-star/10'
            : 'border-gray-600 hover:border-gray-500 hover:bg-white/5'
          }
          ${isLoading ? 'opacity-50 pointer-events-none' : ''}
        `}
        onClick={openFilePicker}
      >
        <div className="text-center">
          <Upload className={`w-10 h-10 mx-auto mb-3 ${isDragOver ? 'text-star' : 'text-gray-400'}`} />
          <p className="text-gray-300 mb-1">
            {t('dragDrop')}
          </p>
          <p className="text-gray-500 text-sm">
            {t('orBrowse')}
          </p>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row gap-4 w-full max-w-md">
        {/* Camera Button (mobile-friendly) */}
        <button
          onClick={openCamera}
          disabled={isLoading}
          className="
            flex-1 flex items-center justify-center gap-3
            bg-white text-black font-semibold py-4 px-6
            rounded-xl transition-all duration-200
            hover:bg-gray-100 active:scale-[0.98]
            disabled:opacity-50 disabled:cursor-not-allowed
          "
        >
          <Camera className="w-5 h-5" />
          {t('takePhoto')}
        </button>

        {/* Upload Button */}
        <button
          onClick={openFilePicker}
          disabled={isLoading}
          className="
            flex-1 flex items-center justify-center gap-3
            bg-white/20 text-white font-semibold py-4 px-6
            rounded-xl transition-all duration-200
            hover:bg-white/30 active:scale-[0.98]
            disabled:opacity-50 disabled:cursor-not-allowed
          "
        >
          <Upload className="w-5 h-5" />
          {t('uploadImage')}
        </button>
      </div>

      {/* Hidden file inputs */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        className="hidden"
      />
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileChange}
        className="hidden"
      />
    </div>
  );
}
