/**
 * Favourite wallets — persisted in localStorage.
 */

const STORAGE_KEY = 'monad-watchdog-favourites';

export interface FavouriteWallet {
  address: string;
  nickname: string; // empty string if none
  addedAt: number;  // unix ms
}

function load(): FavouriteWallet[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function save(favs: FavouriteWallet[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(favs));
}

export function getFavourites(): FavouriteWallet[] {
  return load();
}

export function isFavourite(address: string): boolean {
  return load().some((f) => f.address.toLowerCase() === address.toLowerCase());
}

export function addFavourite(address: string, nickname = '') {
  const favs = load();
  if (favs.some((f) => f.address.toLowerCase() === address.toLowerCase())) return;
  favs.unshift({ address: address.toLowerCase(), nickname, addedAt: Date.now() });
  save(favs);
}

export function removeFavourite(address: string) {
  const favs = load().filter((f) => f.address.toLowerCase() !== address.toLowerCase());
  save(favs);
}

export function toggleFavourite(address: string, nickname = ''): boolean {
  if (isFavourite(address)) {
    removeFavourite(address);
    return false;
  } else {
    addFavourite(address, nickname);
    return true;
  }
}

export function updateNickname(address: string, nickname: string) {
  const favs = load();
  const fav = favs.find((f) => f.address.toLowerCase() === address.toLowerCase());
  if (fav) {
    fav.nickname = nickname;
    save(favs);
  }
}
