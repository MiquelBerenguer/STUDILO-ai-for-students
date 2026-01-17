#!/usr/bin/env python3
"""
Script de Diagnóstico: Encuentra usos incorrectos de .value
Busca patrones problemáticos en el código relacionados con el error:
'str' object has no attribute 'value'
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

class ValueErrorFinder:
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir)
        self.patterns = [
            # Patrón 1: .payload.get('algo').value
            (r"\.payload\.get\(['\"][\w_]+['\"]\)\.value", "❌ CRÍTICO: .payload.get(...).value"),
            
            # Patrón 2: .payload['algo'].value
            (r"\.payload\[['\"][\w_]+['\"]\]\.value", "❌ CRÍTICO: .payload[...].value"),
            
            # Patrón 3: variable.value donde variable podría ser string
            (r"(\w+)\.value(?!\s*=)", "⚠️  SOSPECHOSO: variable.value (revisar tipo)"),
            
            # Patrón 4: result.algo.value (común en respuestas de Qdrant)
            (r"result\.\w+\.value", "⚠️  SOSPECHOSO: result.algo.value"),
            
            # Patrón 5: Acceso a .value en diccionarios
            (r"\.get\(['\"][\w_]+['\"]\)\.value", "❌ CRÍTICO: .get(...).value"),
            
            # Patrón 6: Enum.VALOR.value (esto está bien, pero lo marcamos para verificar)
            (r"[A-Z][a-zA-Z]+\.\w+\.value", "✅ POSIBLE ENUM: verificar si es Enum legítimo"),
        ]
        
        self.exclude_dirs = {
            '__pycache__', '.git', 'node_modules', 'venv', 
            'env', '.venv', 'dist', 'build', '.pytest_cache'
        }
        
        self.target_extensions = {'.py'}
        
    def find_python_files(self) -> List[Path]:
        """Encuentra todos los archivos Python en el proyecto"""
        python_files = []
        
        for root, dirs, files in os.walk(self.root_dir):
            # Excluir directorios no deseados
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for file in files:
                if Path(file).suffix in self.target_extensions:
                    python_files.append(Path(root) / file)
        
        return python_files
    
    def analyze_file(self, filepath: Path) -> List[Tuple[int, str, str, str]]:
        """
        Analiza un archivo y retorna lista de coincidencias
        Returns: [(line_number, line_content, pattern_description, matched_text)]
        """
        findings = []
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"⚠️  No se pudo leer {filepath}: {e}")
            return findings
        
        for line_num, line in enumerate(lines, start=1):
            for pattern, description in self.patterns:
                matches = re.finditer(pattern, line)
                for match in matches:
                    findings.append((
                        line_num,
                        line.strip(),
                        description,
                        match.group(0)
                    ))
        
        return findings
    
    def generate_report(self):
        """Genera el reporte completo de hallazgos"""
        print("🔍 INICIANDO BÚSQUEDA DE ERRORES .value\n")
        print("=" * 80)
        
        python_files = self.find_python_files()
        print(f"📁 Archivos Python encontrados: {len(python_files)}\n")
        
        critical_count = 0
        suspicious_count = 0
        files_with_issues = 0
        
        for filepath in python_files:
            findings = self.analyze_file(filepath)
            
            if not findings:
                continue
            
            files_with_issues += 1
            relative_path = filepath.relative_to(self.root_dir)
            
            print(f"\n{'=' * 80}")
            print(f"📄 ARCHIVO: {relative_path}")
            print(f"{'=' * 80}\n")
            
            for line_num, line_content, description, matched_text in findings:
                severity = "🔴" if "CRÍTICO" in description else "🟡" if "SOSPECHOSO" in description else "🟢"
                
                if "CRÍTICO" in description:
                    critical_count += 1
                elif "SOSPECHOSO" in description:
                    suspicious_count += 1
                
                print(f"{severity} Línea {line_num}: {description}")
                print(f"   Código: {line_content}")
                print(f"   Match:  {matched_text}")
                print()
        
        # Resumen final
        print("\n" + "=" * 80)
        print("📊 RESUMEN DE HALLAZGOS")
        print("=" * 80)
        print(f"🔴 Errores críticos:     {critical_count}")
        print(f"🟡 Casos sospechosos:    {suspicious_count}")
        print(f"📁 Archivos afectados:   {files_with_issues}")
        print("=" * 80)
        
        if critical_count > 0:
            print("\n⚠️  ACCIÓN REQUERIDA:")
            print("   Los errores críticos son la causa probable del problema.")
            print("   Revisa cada línea marcada con 🔴 y elimina el .value")
            print("\n💡 SOLUCIÓN TÍPICA:")
            print("   ❌ difficulty = result.payload.get('difficulty').value")
            print("   ✅ difficulty = result.payload.get('difficulty')")
        
        return critical_count, suspicious_count


def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Busca errores relacionados con .value en código Python'
    )
    parser.add_argument(
        '--path',
        type=str,
        default='.',
        help='Ruta raíz donde buscar (default: directorio actual)'
    )
    
    args = parser.parse_args()
    
    finder = ValueErrorFinder(args.path)
    critical, suspicious = finder.generate_report()
    
    # Exit code para CI/CD
    exit_code = 1 if critical > 0 else 0
    exit(exit_code)


if __name__ == "__main__":
    main()