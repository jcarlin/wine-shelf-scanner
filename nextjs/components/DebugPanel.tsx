'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, FlaskConical } from 'lucide-react';
import { DebugData, DebugPipelineStep, NearMissCandidate, NormalizationTrace, LLMRawDebug } from '@/lib/types';
import { colors } from '@/lib/theme';

interface DebugPanelProps {
  data: DebugData;
}

function NormalizationTraceSection({ trace }: { trace: NormalizationTrace }) {
  return (
    <div className="mt-1 p-2 rounded bg-white/5">
      <div className="text-gray-400 font-semibold mb-1" style={{ color: '#8B5CF6' }}>
        Normalization Trace
      </div>
      <div className="space-y-1 font-mono text-[10px]">
        <div>
          <span className="text-gray-500">Original: </span>
          <span className="text-gray-300">{trace.original_text}</span>
        </div>
        {trace.removed_patterns.length > 0 && (
          <div>
            <span className="text-gray-500">Removed patterns: </span>
            {trace.removed_patterns.map((p, i) => (
              <span key={i} className="inline-block px-1 py-0.5 mx-0.5 rounded text-red-300 bg-red-900/30">{p}</span>
            ))}
          </div>
        )}
        <div>
          <span className="text-gray-500">After patterns: </span>
          <span className="text-gray-300">{trace.after_pattern_removal}</span>
        </div>
        {trace.removed_filler_words.length > 0 && (
          <div>
            <span className="text-gray-500">Removed fillers: </span>
            {trace.removed_filler_words.map((w, i) => (
              <span key={i} className="inline-block px-1 py-0.5 mx-0.5 rounded text-amber-300 bg-amber-900/30">{w}</span>
            ))}
          </div>
        )}
        <div>
          <span className="text-gray-500">Final: </span>
          <span className="text-white font-semibold">{trace.final_text || '(empty)'}</span>
        </div>
      </div>
    </div>
  );
}

function NearMissSection({ nearMisses }: { nearMisses: NearMissCandidate[] }) {
  return (
    <div className="mt-1.5 pt-1.5 border-t border-white/5">
      <div className="text-amber-400 text-[10px] font-semibold mb-1">Near-Miss Candidates</div>
      <div className="space-y-0.5">
        {nearMisses.map((nm, i) => (
          <div key={i} className="flex items-center gap-2 px-1.5 py-0.5 rounded bg-amber-900/15">
            <span className="text-gray-300 flex-1 truncate">{nm.wine_name}</span>
            <span className="text-amber-300 font-mono shrink-0">{nm.score.toFixed(2)}</span>
            <span className="text-gray-500 text-[9px] shrink-0">{nm.rejection_reason}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LLMRawSection({ llmRaw }: { llmRaw: LLMRawDebug }) {
  const [showRaw, setShowRaw] = useState(false);

  if (llmRaw.was_heuristic_fallback) {
    return (
      <div className="mt-1 p-2 rounded bg-white/5">
        <div className="text-gray-400 font-semibold mb-1">
          LLM Raw
          <span className="ml-2 text-[9px] px-1.5 py-0.5 rounded bg-amber-800/40 text-amber-300">heuristic fallback</span>
        </div>
        <div className="text-gray-500 text-[10px]">LLM not called — used heuristic validation</div>
      </div>
    );
  }

  return (
    <div className="mt-1 p-2 rounded bg-white/5">
      <button
        onClick={() => setShowRaw(!showRaw)}
        className="flex items-center gap-1.5 text-gray-400 font-semibold hover:text-gray-300 transition-colors"
      >
        {showRaw ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        <span>LLM Raw</span>
        {llmRaw.model_used && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-900/40 text-blue-300 font-normal">{llmRaw.model_used}</span>
        )}
      </button>
      {showRaw && (
        <div className="mt-1.5 space-y-1.5">
          <div>
            <div className="text-gray-500 text-[10px] mb-0.5">Prompt (truncated):</div>
            <pre className="text-[10px] text-gray-400 bg-black/30 p-1.5 rounded overflow-x-auto whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
              {llmRaw.prompt_text}
            </pre>
          </div>
          <div>
            <div className="text-gray-500 text-[10px] mb-0.5">Response (truncated):</div>
            <pre className="text-[10px] text-gray-400 bg-black/30 p-1.5 rounded overflow-x-auto whitespace-pre-wrap break-all max-h-32 overflow-y-auto">
              {llmRaw.raw_response}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
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

          {/* Normalization Trace */}
          {step.normalization_trace && (
            <NormalizationTraceSection trace={step.normalization_trace} />
          )}

          {step.fuzzy_match && (
            <div className="mt-1 p-2 rounded bg-white/5">
              <div className="text-gray-400 font-semibold mb-1">Fuzzy Match</div>
              {step.fuzzy_match.candidate ? (
                <>
                  <div>
                    <span className="text-gray-500">Candidate: </span>
                    <span className="text-gray-300">{step.fuzzy_match.candidate}</span>
                  </div>
                  {step.fuzzy_match.scores && (
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                      <span className="text-gray-500">ratio: <span className="text-gray-300">{step.fuzzy_match.scores.ratio.toFixed(2)}</span></span>
                      <span className="text-gray-500">partial: <span className="text-gray-300">{step.fuzzy_match.scores.partial_ratio.toFixed(2)}</span></span>
                      <span className="text-gray-500">token_sort: <span className="text-gray-300">{step.fuzzy_match.scores.token_sort_ratio.toFixed(2)}</span></span>
                      <span className="text-gray-500">phonetic: <span className="text-gray-300">{step.fuzzy_match.scores.phonetic_bonus.toFixed(2)}</span></span>
                      <span className="text-gray-400 font-semibold">weighted: <span className="text-white">{step.fuzzy_match.scores.weighted_score.toFixed(2)}</span></span>
                    </div>
                  )}
                  {step.fuzzy_match.rating !== null && (
                    <div className="mt-0.5">
                      <span className="text-gray-500">DB rating: </span>
                      <span className="text-gray-300">{step.fuzzy_match.rating.toFixed(1)}</span>
                    </div>
                  )}
                </>
              ) : (
                <div>
                  <span className="text-gray-500">No match found</span>
                  {step.fuzzy_match.rejection_reason && (
                    <span className="text-amber-400 ml-2">({step.fuzzy_match.rejection_reason})</span>
                  )}
                </div>
              )}
              {step.fuzzy_match.fts_candidates_count !== undefined && step.fuzzy_match.fts_candidates_count > 0 && (
                <div className="mt-0.5">
                  <span className="text-gray-500">FTS candidates searched: </span>
                  <span className="text-gray-300">{step.fuzzy_match.fts_candidates_count}</span>
                </div>
              )}

              {/* Near-Miss Candidates */}
              {step.fuzzy_match.near_misses && step.fuzzy_match.near_misses.length > 0 && (
                <NearMissSection nearMisses={step.fuzzy_match.near_misses} />
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

          {/* LLM Raw Prompt/Response */}
          {step.llm_raw && (
            <LLMRawSection llmRaw={step.llm_raw} />
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
