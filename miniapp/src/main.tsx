import { render } from 'preact';
import { TwinDashboard } from './views/TwinDashboard';
import './styles.css';

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string;
        themeParams?: Record<string, string>;
        ready: () => void;
        expand: () => void;
        showAlert?: (message: string) => void;
      };
    };
  }
}

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

render(<TwinDashboard telegramInitData={tg?.initData ?? ''} />, document.getElementById('app')!);
