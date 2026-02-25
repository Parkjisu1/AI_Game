using UnityEngine;

namespace BlockBlast.Core
{
    public class SaveManager : Singleton<SaveManager>
    {
        public const string KEY_HIGH_SCORE = "HighScore";
        public const string KEY_SOUND_ON = "SoundOn";
        public const string KEY_VIBRATION_ON = "VibrationOn";
        public const string KEY_GAMES_PLAYED = "GamesPlayed";
        public const string KEY_REMOVE_ADS = "RemoveAds";

        public void SaveInt(string key, int value)
        {
            PlayerPrefs.SetInt(key, value);
            PlayerPrefs.Save();
        }

        public int LoadInt(string key, int defaultValue = 0)
        {
            return PlayerPrefs.GetInt(key, defaultValue);
        }

        public void SaveString(string key, string value)
        {
            PlayerPrefs.SetString(key, value);
            PlayerPrefs.Save();
        }

        public string LoadString(string key, string defaultValue = "")
        {
            return PlayerPrefs.GetString(key, defaultValue);
        }

        public bool HasKey(string key)
        {
            return PlayerPrefs.HasKey(key);
        }

        public void DeleteKey(string key)
        {
            PlayerPrefs.DeleteKey(key);
            PlayerPrefs.Save();
        }

        public int GetHighScore()
        {
            return LoadInt(KEY_HIGH_SCORE, 0);
        }

        public bool SetHighScore(int score)
        {
            int current = GetHighScore();
            if (score > current)
            {
                SaveInt(KEY_HIGH_SCORE, score);
                return true;
            }
            return false;
        }

        public int IncrementGamesPlayed()
        {
            int count = LoadInt(KEY_GAMES_PLAYED, 0) + 1;
            SaveInt(KEY_GAMES_PLAYED, count);
            return count;
        }

        public bool IsAdsRemoved()
        {
            return LoadInt(KEY_REMOVE_ADS, 0) == 1;
        }

        public void SetAdsRemoved()
        {
            SaveInt(KEY_REMOVE_ADS, 1);
        }
    }
}
