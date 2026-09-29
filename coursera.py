import pandas as pd
import numpy as np
import random
from datetime import timedelta
import re
import sqlite3
from transformers import pipeline
from tqdm import tqdm

def run_pipeline():
    print("Iniciando pipeline de procesamiento de datos...")
    
    try:
        df_reviews = pd.read_csv('Coursera_reviews.csv')
        df_faq = pd.read_csv('datafaq_enriched.csv')
    except FileNotFoundError:
        print("Error: Archivos CSV fuente no encontrados en el directorio.")
        return

    df_reviews['date_reviews'] = pd.to_datetime(df_reviews['date_reviews'], errors='coerce')

    print("Aplicando filtros de dominio y limites de registros...")
    keywords = ['data-science', 'datascience', 'machine', 'deep', 'neural', 'neuronal', r'\bml\b']
    pattern = '|'.join(keywords)
    
    df_filtrado = df_reviews[df_reviews['course_id'].str.contains(pattern, case=False, na=False, regex=True)].copy()
    df_filtrado = df_filtrado.dropna(subset=['reviews', 'rating'])
    
    df_filtrado = df_filtrado.sample(frac=1, random_state=1)
    df_filtrado = df_filtrado.groupby('course_id').head(100).reset_index(drop=True)
    total_reviews_puras = len(df_filtrado)

    print("Estructurando columnas y normalizando texto...")
    df_filtrado['faq_answer'] = pd.NA
    df_filtrado['is_faq'] = False

    def limpiar_texto(texto):
        if not isinstance(texto, str): return ""
        texto = str(texto).lower()
        texto = re.sub(r'<.*?>', '', texto)
        texto = re.sub(r'[^\w\s]', '', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        return texto

    df_filtrado['reviews_clean'] = df_filtrado['reviews'].apply(limpiar_texto)

    print("Integrando base de conocimientos FAQ...")
    RATIO = 20
    faqs_necesarias = total_reviews_puras // RATIO
    veces_a_repetir = int(np.ceil(faqs_necesarias / len(df_faq)))
    df_faq_multiplicado = pd.concat([df_faq] * veces_a_repetir, ignore_index=True).head(faqs_necesarias)

    nombres_base = ['Data Mentor', 'Course Assistant', 'Support', 'Prof. Ng', 'Data Scientist']
    nombres_inventados = [random.choice(nombres_base) for _ in range(len(df_faq_multiplicado))]

    fecha_min = df_filtrado['date_reviews'].min()
    fecha_max = df_filtrado['date_reviews'].max()
    dias_diferencia = (fecha_max - fecha_min).days
    fechas_inventadas = [fecha_min + timedelta(days=random.randint(0, dias_diferencia)) for _ in range(len(df_faq_multiplicado))]

    cursos_disponibles = df_filtrado['course_id'].dropna().unique()
    cursos_inventados = [random.choice(cursos_disponibles) for _ in range(len(df_faq_multiplicado))]

    df_faq_adaptado = pd.DataFrame({
        'reviews': df_faq_multiplicado['Question'],
        'faq_answer': df_faq_multiplicado['Answer'],
        'is_faq': True,
        'reviewers': nombres_inventados,
        'date_reviews': fechas_inventadas,
        'rating': 5,
        'course_id': cursos_inventados,
        'reviews_clean': df_faq_multiplicado['Question'].apply(limpiar_texto)
    })

    df_maestro = pd.concat([df_filtrado, df_faq_adaptado], ignore_index=True)
    df_maestro = df_maestro.sample(frac=1, random_state=42).reset_index(drop=True)

    print("Inicializando modelo de analisis de sentimientos...")
    analyzer_multi = pipeline(
        "sentiment-analysis",
        model="cardiffnlp/twitter-xlm-roberta-base-sentiment",
        tokenizer="cardiffnlp/twitter-xlm-roberta-base-sentiment",
        device=-1 
    )

    def analizar_sentimiento(fila):
        if fila['is_faq']: 
            return "FAQ Educativo"
        texto = str(fila['reviews'])
        if not texto.strip(): 
            return "Neutral"
        try:
            resultado = analyzer_multi(texto, truncation=True, max_length=512)[0]
            label = resultado['label']
            if label in ['LABEL_0', 'negative']: return "Negativo"
            elif label in ['LABEL_1', 'neutral']: return "Neutral"
            elif label in ['LABEL_2', 'positive']: return "Positivo"
            else: return "Neutral"
        except:
            return "Neutral"

    tqdm.pandas(desc="Procesando sentimientos")
    df_maestro['sentiment'] = df_maestro.progress_apply(analizar_sentimiento, axis=1)

    print("Exportando datos a base de datos relacional...")
    db_name = 'motor_educativo.db'
    conexion = sqlite3.connect(db_name)
    df_maestro.to_sql('contenido_educativo', conexion, if_exists='replace', index=False)
    conexion.close()

    print("Pipeline finalizado exitosamente.")

if __name__ == "__main__":
    run_pipeline()
