import os

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier


def synthesize_dataset(samples=10000):
    """
    Synthesizes a structured tabular dataset mimicking TapeRadar's feature dimensions.
    Because the SQLite `backtest.db` doesn't have 10k closed historical loop cycles recorded yet, 
    we bootstrap the XGBClassifier matrix by injecting perfect heuristic rule-imitations so the 
    neural-structure fundamentally grasps the existing physics before adapting to live-stream data.
    """
    np.random.seed(42)
    
    # 25+ Features standard across our pipeline
    df = pd.DataFrame({
        'day_change_pct': np.random.uniform(-15.0, 35.0, samples),
        'pos_in_range': np.random.uniform(0.0, 1.0, samples),
        'quote_vol_24h': np.random.uniform(1e5, 5e8, samples),
        'rsi_1h': np.random.uniform(10, 90, samples),
        'macd_1h': np.random.uniform(-50, 50, samples),
        'rsi_15m': np.random.uniform(10, 90, samples),
        'bb_width_1h': np.random.uniform(0.01, 0.15, samples),
        'bb_pct_b_1h': np.random.uniform(-0.1, 1.1, samples),
        'volume_ratio_1h': np.random.uniform(0.1, 5.0, samples),
        
        # Options derivatives
        'iv_skew': np.random.uniform(-0.10, 0.10, samples),  # - = Calls, + = Puts
        'gamma_wall_proximity': np.random.uniform(0.0, 0.05, samples),
        
        # TapeRadar Custom Beta Metric
        'rs_vs_btc': np.random.uniform(-10.0, 15.0, samples)
    })
    
    # Define Target Logic (1 = Multi-target WIN, 0 = Stopped out / Chop)
    # The neural network has to figure out these non-linear conditions mathematically!
    win_probability = np.zeros(samples)
    
    # Rules:
    # 1. High Relative Strength (Beta) > +2% adds heavy probability
    # 2. Bullish IV Skew (Greed) adds prob, High Put Skew (Fear) subtracts
    # 3. Low RSI (< 35) but high volume ratio (dip buying)
    # 4. CHASE setups (PIR > 0.85 & Day Change > 15) fail terribly
    
    for i in range(samples):
        prob = 0.50
        
        row = df.iloc[i]
        if row['rs_vs_btc'] > 2.0:
            prob += 0.20
        elif row['rs_vs_btc'] < -2.0:
            prob -= 0.15

        # Fear (puts bid) is bearish, greed (calls bid) is bullish.
        if row['iv_skew'] > 0.03:
            prob -= 0.10
        elif row['iv_skew'] < -0.03:
            prob += 0.15
        
        if row['rsi_1h'] < 35 and row['volume_ratio_1h'] > 1.5:
            prob += 0.25 # Coiled spring setup
            
        if row['pos_in_range'] > 0.85 and row['day_change_pct'] > 15:
            prob -= 0.40 # Exhaustion Chase
            
        # Add realistic market noise
        noise = np.random.normal(0, 0.1)
        final_prob = max(0.0, min(1.0, prob + noise))
        
        # Binary target via threshold
        win_probability[i] = 1 if final_prob > 0.65 else 0
        
    df['target'] = win_probability
    return df

def train_evaluator_model():
    print("Initiating XGBoost Quantitative Training Grid...")
    df = synthesize_dataset(15000)
    
    X = df.drop(columns=['target'])
    y = df['target']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print(f"Training parameters dimensions: {X_train.shape}")
    model = XGBClassifier(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric='logloss',
        random_state=42
    )
    
    model.fit(X_train, y_train)
    
    preds = model.predict(X_test)
    print("\n--- TapeRadar Neural Weights Output ---")
    print(f"Accuracy: {accuracy_score(y_test, preds):.4f}")
    print(f"Precision: {precision_score(y_test, preds):.4f}")
    
    # Save the completed algorithmic model to binary
    output_dir = os.path.dirname(__file__)
    model_path = os.path.join(output_dir, 'taperadar_xgboost_v1.joblib')
    joblib.dump(model, model_path)
    
    print(f"Model successfully saved to {model_path}")
    
if __name__ == "__main__":
    train_evaluator_model()
