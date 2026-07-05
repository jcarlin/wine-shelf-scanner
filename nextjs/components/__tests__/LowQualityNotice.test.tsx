/**
 * LowQualityNotice — shown when the backend's input-quality gate rejects a
 * scan (median detected bottle width below the legibility floor). The user
 * must never hit a dead end: the notice explains the problem and offers a
 * retake.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { LowQualityNotice } from '../LowQualityNotice';

// Render translation keys verbatim so assertions are locale-independent.
jest.mock('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}));

describe('LowQualityNotice', () => {
  it('explains the problem and offers a retake', () => {
    render(<LowQualityNotice onReset={jest.fn()} />);

    expect(screen.getByText('fallback.tooFarTitle')).toBeInTheDocument();
    expect(screen.getByText('fallback.tooFarMessage')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'fallback.retake' })).toBeInTheDocument();
  });

  it('calls onReset when the retake button is pressed', () => {
    const onReset = jest.fn();
    render(<LowQualityNotice onReset={onReset} />);

    fireEvent.click(screen.getByRole('button', { name: 'fallback.retake' }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
