import {
  getMockResponse,
  getMockResponseForTest,
} from '../mock-service';

describe('mock-service', () => {
  describe('getMockResponse', () => {
    it('should return full_shelf response with 8 wines', async () => {
      const response = await getMockResponse('full_shelf', { delay: 0 });

      expect(response.image_id).toMatch(/^mock-/);
      expect(response.results).toHaveLength(8);
      expect(response.fallback_list).toHaveLength(0);
    });

    it('should return partial_detection response with 3 results and 5 fallbacks', async () => {
      const response = await getMockResponse('partial_detection', { delay: 0 });

      expect(response.results).toHaveLength(3);
      expect(response.fallback_list).toHaveLength(5);
    });

    it('should return low_confidence response with low confidence scores', async () => {
      const response = await getMockResponse('low_confidence', { delay: 0 });

      expect(response.results).toHaveLength(4);
      response.results.forEach((wine) => {
        expect(wine.confidence).toBeLessThan(0.65);
      });
    });

    it('should return empty_results response with only fallbacks', async () => {
      const response = await getMockResponse('empty_results', { delay: 0 });

      expect(response.results).toHaveLength(0);
      expect(response.fallback_list.length).toBeGreaterThan(0);
    });

    it('should simulate delay', async () => {
      const startTime = Date.now();
      await getMockResponse('full_shelf', { delay: 100 });
      const elapsed = Date.now() - startTime;

      expect(elapsed).toBeGreaterThanOrEqual(90); // Allow some tolerance
    });

    it('should throw error when simulateError is true', async () => {
      await expect(
        getMockResponse('full_shelf', {
          delay: 0,
          simulateError: true,
          errorMessage: 'Test error',
        })
      ).rejects.toThrow('Test error');
    });

    it('should throw default error message when simulateError is true but no message provided', async () => {
      await expect(
        getMockResponse('full_shelf', {
          delay: 0,
          simulateError: true,
        })
      ).rejects.toThrow('Mock error');
    });
  });

  describe('getMockResponseForTest', () => {
    it('should return response with minimal delay', async () => {
      const startTime = Date.now();
      await getMockResponseForTest('full_shelf');
      const elapsed = Date.now() - startTime;

      // Should complete quickly (100ms default test delay)
      expect(elapsed).toBeLessThan(200);
    });
  });

  describe('wine data structure', () => {
    it('should have correct WineResult structure', async () => {
      const response = await getMockResponse('full_shelf', { delay: 0 });
      const wine = response.results[0];

      expect(wine).toHaveProperty('wine_name');
      expect(wine).toHaveProperty('rating');
      expect(wine).toHaveProperty('confidence');
      expect(wine).toHaveProperty('bbox');
      expect(wine.bbox).toHaveProperty('x');
      expect(wine.bbox).toHaveProperty('y');
      expect(wine.bbox).toHaveProperty('width');
      expect(wine.bbox).toHaveProperty('height');
    });

    it('should have correct FallbackWine structure', async () => {
      const response = await getMockResponse('partial_detection', { delay: 0 });
      const fallback = response.fallback_list[0];

      expect(fallback).toHaveProperty('wine_name');
      expect(fallback).toHaveProperty('rating');
    });

    it('should have normalized bbox values (0-1)', async () => {
      const response = await getMockResponse('full_shelf', { delay: 0 });

      response.results.forEach((wine) => {
        expect(wine.bbox.x).toBeGreaterThanOrEqual(0);
        expect(wine.bbox.x).toBeLessThanOrEqual(1);
        expect(wine.bbox.y).toBeGreaterThanOrEqual(0);
        expect(wine.bbox.y).toBeLessThanOrEqual(1);
        expect(wine.bbox.width).toBeGreaterThanOrEqual(0);
        expect(wine.bbox.width).toBeLessThanOrEqual(1);
        expect(wine.bbox.height).toBeGreaterThanOrEqual(0);
        expect(wine.bbox.height).toBeLessThanOrEqual(1);
      });
    });

    it('should have ratings in valid range (1-5)', async () => {
      const response = await getMockResponse('full_shelf', { delay: 0 });

      response.results.forEach((wine) => {
        expect(wine.rating).toBeGreaterThanOrEqual(1);
        expect(wine.rating).toBeLessThanOrEqual(5);
      });
    });

    it('should have confidence in valid range (0-1)', async () => {
      const response = await getMockResponse('full_shelf', { delay: 0 });

      response.results.forEach((wine) => {
        expect(wine.confidence).toBeGreaterThanOrEqual(0);
        expect(wine.confidence).toBeLessThanOrEqual(1);
      });
    });
  });

  describe('scenario-specific data', () => {
    it('full_shelf should have known wines', async () => {
      const response = await getMockResponse('full_shelf', { delay: 0 });
      const wineNames = response.results.map((w) => w.wine_name);

      expect(wineNames).toContain('Caymus Cabernet Sauvignon');
      expect(wineNames).toContain('Opus One');
      expect(wineNames).toContain('Silver Oak Alexander Valley');
    });

    it('full_shelf top 3 should have highest ratings', async () => {
      const response = await getMockResponse('full_shelf', { delay: 0 });
      const sorted = [...response.results].sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
      const top3 = sorted.slice(0, 3);

      // Opus One should be highest (4.8)
      expect(top3[0].wine_name).toBe('Opus One');
    });

    it('partial_detection should trigger fallback list display', async () => {
      const response = await getMockResponse('partial_detection', { delay: 0 });

      // This scenario has both results and fallbacks - triggers partial detection UI
      expect(response.results.length).toBeGreaterThan(0);
      expect(response.fallback_list.length).toBeGreaterThan(0);
    });

    it('empty_results should trigger full failure flow', async () => {
      const response = await getMockResponse('empty_results', { delay: 0 });

      // Empty results with fallbacks triggers full failure UI
      expect(response.results).toHaveLength(0);
      expect(response.fallback_list.length).toBeGreaterThan(0);
    });
  });
});
