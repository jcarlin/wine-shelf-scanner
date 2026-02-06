'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, FlaskConical } from 'lucide-react';
import { DebugData, DebugPipelineStep } from '@/lib/types';
import { colors } from '@/lib/theme';

interface DebugPanelProps {
  data: DebugData;
}

function StepRow({ step, index }: { step: DebugPipelineStep; index: number }) {
  const [expanded, setExpanded] = useState(false);

  const statusColor = step.included_in_results
    ? colors.statusSuccess
    : step.step_failed
      ? colors.statusFailure
      : colors.statusWarning;

  const sourceLabel = step.final_result?.source === 'llm'
    ? 'LLM'
    : step.final_result?.source === 'fuzzy'
      ? 'Fuzzy'
      : 'No match';

  const sourceBadgeColor = step.final_result?.source === 'llm'
    ? colors.debugOrange
    : step.final_result?.source === 'fuzzy'
      ? colors.statusSuccess
      : colors.statusFailure;

  return (
    <div
      className="border-b border-white/10 last:border-b-0"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/5 transition-colors"
      >
        {expanded
          ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 shrink-0" />
          : <ChevronRight className="w-3.5 h-3.5 text-gray-400 shrink-0" />
        }
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ backgroundColor: statusColor }}
        />
        <span className="text-xs text-gray-300 truncate flex-1 font-mono">
          {step.normalized_text || step.raw_text}
        </span>
        <span
          className="text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0"
          style={{ backgroundColor: sourceBadgeColor, color: '#000' }}
        >
          {sourceLabel}
        </span>
        {step.final_result && (
          <span className="text-[10px] text-gray-500 shrink-0">
            {(step.final_result.confidence * 100).toFixed(0)}%
          </span>
        )}
      </button>

      {expanded && (
        <div className="px-3 pb-3 pl-9 space-y-1.5 text-[11px]">
          <div>
            <span className="text-gray-500">Raw OCR: </span>
            <span className="text-gray-300 font-mono">{step.raw_text}</span>
          </div>
          <div>
            <span className="text-gray-500">Normalized: </span>
            <span className="text-gray-300 font-mono">{step.normalized_text}</span>
          </div>
          {step.bottle_index !== null && (
            <div>
              <span className="text-gray-500">Bottle: </span>
              <span className="text-gray-300">#{step.bottle_index}</span>
            </div>
          )}

          {step.fuzzy_match && (
            <div className="mt-1 p-2 rounded bg-white/5">
              <div className="text-gray-400 font-semibold mb-1">Fuzzy Match</div>
              <div>
                <span className="text-gray-500">Candidate: </span>
                <span className="text-gray-300">{step.fuzzy_match.candidate}</span>
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                <span className="text-gray-500">ratio: <span className="text-gray-300">{step.fuzzy_match.scores.ratio.toFixed(0)}</span></span>
                <span className="text-gray-500">partial: <span className="text-gray-300">{step.fuzzy_match.scores.partial_ratio.toFixed(0)}</span></span>
                <span className="text-gray-500">token_sort: <span className="text-gray-300">{step.fuzzy_match.scores.token_sort_ratio.toFixed(0)}</span></span>
                <span className="text-gray-500">phonetic: <span className="text-gray-300">{step.fuzzy_match.scores.phonetic_bonus.toFixed(0)}</span></span>
                <span className="text-gray-400 font-semibold">weighted: <span className="text-white">{step.fuzzy_match.scores.weighted_score.toFixed(1)}</span></span>
              </div>
              {step.fuzzy_match.rating !== null && (
                <div className="mt-0.5">
                  <span className="text-gray-500">DB rating: </span>
                  <span className="text-gray-300">{step.fuzzy_match.rating.toFixed(1)}</span>
                </div>
              )}
            </div>
          )}

          {step.llm_validation && (
            <div className="mt-1 p-2 rounded bg-white/5">
              <div className="text-gray-400 font-semibold mb-1" style={{ color: colors.debugOrange }}>
                LLM Validation
              </div>
              <div>
                <span className="text-gray-500">Valid: </span>
                <span style={{ color: step.llm_validation.is_valid_match ? colors.statusSuccess : colors.statusFailure }}>
                  {step.llm_validation.is_valid_match ? 'Yes' : 'No'}
                </span>
              </div>
              {step.llm_validation.wine_name && (
                <div>
                  <span className="text-gray-500">Wine: </span>
                  <span className="text-gray-300">{step.llm_validation.wine_name}</span>
                </div>
              )}
              {step.llm_validation.confidence !== null && (
                <div>
                  <span className="text-gray-500">Confidence: </span>
                  <span className="text-gray-300">{(step.llm_validation.confidence * 100).toFixed(0)}%</span>
                </div>
              )}
              {step.llm_validation.reasoning && (
                <div>
                  <span className="text-gray-500">Reasoning: </span>
                  <span className="text-gray-400 italic">{step.llm_validation.reasoning}</span>
                </div>
              )}
            </div>
          )}

          {step.final_result && (
            <div className="mt-1">
              <span className="text-gray-500">Result: </span>
              <span className="text-white font-medium">{step.final_result.wine_name}</span>
              <span className="text-gray-500 ml-2">
                ({step.final_result.source}, {(step.final_result.confidence * 100).toFixed(0)}%)
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function DebugPanel({ data }: DebugPanelProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="border-t border-white/10"
      style={{ backgroundColor: colors.debugBackground }}
    >
      {/* Summary bar — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/5 transition-colors"
        style={{ backgroundColor: colors.debugHeaderBackground }}
      >
        <FlaskConical className="w-4 h-4 shrink-0" style={{ color: colors.debugOrange }} />
        <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-gray-400 flex-1 min-w-0">
          <span>Bottles: <span className="text-white font-medium">{data.bottles_detected}</span></span>
          <span>OCR texts: <span className="text-white font-medium">{data.total_ocr_texts}</span></span>
          <span>Matched: <span className="text-white font-medium">{data.texts_matched}</span></span>
          <span>LLM calls: <span className="text-white font-medium">{data.llm_calls_made}</span></span>
        </div>
        {expanded
          ? <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
          : <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
        }
      </button>

      {/* Pipeline steps — expandable */}
      {expanded && (
        <div className="max-h-[50vh] overflow-y-auto">
          {data.pipeline_steps.map((step, i) => (
            <StepRow key={i} step={step} index={i} />
          ))}
          {data.pipeline_steps.length === 0 && (
            <div className="px-4 py-3 text-xs text-gray-500">No pipeline steps recorded.</div>
          )}
        </div>
      )}
    </div>
  );
}
