/**
 * Combine class names, filtering falsy values.
 *
 * @param values - Candidate class names.
 * @returns Joined class string.
 */
export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(' ');
}

/**
 * Format an ISO date string for display.
 *
 * @param value - ISO date string.
 * @returns Localized date string.
 */
export function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

/**
 * Extract a readable API error message.
 *
 * @param error - Unknown thrown value.
 * @returns Human-readable message.
 */
export function getErrorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { message?: string } } }).response;
    if (response?.data?.message) {
      return response.data.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Something went wrong';
}
