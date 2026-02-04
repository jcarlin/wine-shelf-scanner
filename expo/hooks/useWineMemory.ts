import { useState, useEffect, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

export type WineSentiment = 'liked' | 'disliked';

interface WineMemoryEntry {
  wine_name: string;
  sentiment: WineSentiment;
  timestamp: string; // ISO 8601
}

const STORAGE_KEY = 'wine_memory';
const MAX_ENTRIES = 500;

type MemoryMap = Record<string, WineMemoryEntry>;

export function useWineMemory() {
  const [memory, setMemory] = useState<MemoryMap>({});
  const [loaded, setLoaded] = useState(false);

  // Load from AsyncStorage on mount
  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((data) => {
      if (data) {
        try {
          setMemory(JSON.parse(data));
        } catch {
          // Corrupted data, start fresh
        }
      }
      setLoaded(true);
    });
  }, []);

  // Persist whenever memory changes (after initial load)
  useEffect(() => {
    if (loaded) {
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(memory));
    }
  }, [memory, loaded]);

  const save = useCallback((wineName: string, sentiment: WineSentiment) => {
    setMemory((prev) => {
      const key = wineName.toLowerCase();
      const next: MemoryMap = {
        ...prev,
        [key]: {
          wine_name: wineName,
          sentiment,
          timestamp: new Date().toISOString(),
        },
      };
      // LRU eviction if over limit
      const keys = Object.keys(next);
      if (keys.length > MAX_ENTRIES) {
        const sorted = keys.sort(
          (a, b) => new Date(next[a].timestamp).getTime() - new Date(next[b].timestamp).getTime()
        );
        const toRemove = keys.length - MAX_ENTRIES;
        for (let i = 0; i < toRemove; i++) {
          delete next[sorted[i]];
        }
      }
      return next;
    });
  }, []);

  const get = useCallback(
    (wineName: string): WineSentiment | undefined => {
      const key = wineName.toLowerCase();
      return memory[key]?.sentiment;
    },
    [memory]
  );

  const clear = useCallback((wineName: string) => {
    setMemory((prev) => {
      const key = wineName.toLowerCase();
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  return { save, get, clear, loaded };
}
