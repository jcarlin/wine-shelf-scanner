'use client';

import { useState } from 'react';
import { X, Flag, CheckCircle, AlertTriangle, XCircle, ArrowLeftRight } from 'lucide-react';
import { BugReportType, BugReportMetadata } from '@/lib/types';
import { submitBugReport, inferErrorType } from '@/lib/report-client';

interface BugReportModalProps {
  isOpen: boolean;
  onClose: () => void;
  reportType: BugReportType;
  errorMessage?: string | null;
  imageId?: string | null;
  metadata?: BugReportMetadata | null;
}

const contextConfig: Record<BugReportType, { label: string; icon: typeof AlertTriangle }> = {
  error: { label: 'Scan error', icon: AlertTriangle },
  partial_detection: { label: 'Some bottles not recognized', icon: AlertTriangle },
  full_failure: { label: 'No bottles identified', icon: XCircle },
  wrong_wine: { label: 'Wrong wine match', icon: ArrowLeftRight },
};

export function BugReportModal({
  isOpen,
  onClose,
  reportType,
  errorMessage,
  imageId,
  metadata,
}: BugReportModalProps) {
  const [userDescription, setUserDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  if (!isOpen) return null;

  const config = contextConfig[reportType];
  const ContextIcon = config.icon;

  const handleSubmit = async () => {
    setIsSubmitting(true);
    await submitBugReport({
      reportType,
      errorType: errorMessage ? inferErrorType(errorMessage) : null,
      errorMessage,
      userDescription: userDescription.trim() || null,
      imageId,
      metadata,
    });
    // Always show success (fire-and-forget)
    setSubmitted(true);
    setIsSubmitting(false);
  };

  const handleClose = () => {
    setUserDescription('');
    setSubmitted(false);
    setIsSubmitting(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md bg-gray-900 rounded-t-2xl sm:rounded-2xl p-6 z-10 max-h-[80vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Flag className="w-5 h-5" />
            Report an Issue
          </h2>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white transition-colors p-1"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {submitted ? (
          /* Confirmation */
          <div className="text-center py-8">
            <CheckCircle className="w-12 h-12 text-green-400 mx-auto mb-3" />
            <p className="text-white font-medium mb-1">Report submitted</p>
            <p className="text-gray-400 text-sm mb-6">
              Thanks for helping us improve!
            </p>
            <button
              onClick={handleClose}
              className="bg-white text-black font-semibold py-2.5 px-8 rounded-xl hover:bg-gray-100 transition-colors"
            >
              Done
            </button>
          </div>
        ) : (
          /* Report Form */
          <div className="space-y-4">
            {/* Context */}
            <div className="bg-white/5 rounded-lg p-3">
              <div className="flex items-center gap-2 text-gray-300 text-sm">
                <ContextIcon className="w-4 h-4 text-yellow-400" />
                <span>{config.label}</span>
              </div>
              {errorMessage && (
                <p className="text-gray-500 text-xs mt-1 line-clamp-2">
                  {errorMessage}
                </p>
              )}
            </div>

            {/* User description */}
            <div>
              <label className="text-sm text-gray-400 block mb-1.5">
                What happened? (optional)
              </label>
              <textarea
                value={userDescription}
                onChange={(e) => setUserDescription(e.target.value)}
                placeholder="Describe the issue..."
                maxLength={500}
                rows={3}
                className="w-full bg-white/5 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm placeholder:text-gray-600 focus:outline-none focus:border-gray-500 resize-none"
              />
              <p className="text-gray-600 text-xs text-right mt-0.5">
                {userDescription.length}/500
              </p>
            </div>

            {/* Submit */}
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="w-full bg-white text-black font-semibold py-3 rounded-xl hover:bg-gray-100 transition-colors disabled:opacity-50"
            >
              {isSubmitting ? 'Submitting...' : 'Submit Report'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
