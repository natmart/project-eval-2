#!/usr/bin/env python3
"""
Manual Coverage Analysis Script
Analyzes test files and source files to estimate coverage
"""

import os
import re
import ast
from pathlib import Path
from collections import defaultdict


class CoverageAnalyzer:
    def __init__(self, source_dir, test_dir):
        self.source_dir = Path(source_dir)
        self.test_dir = Path(test_dir)
        self.source_files = {}
        self.test_files = {}
        self.coverage_map = defaultdict(lambda: {
            'functions': set(),
            'classes': set(),
            'tested_functions': set(),
            'tested_classes': set(),
            'lines': 0,
        })

    def get_all_python_files(self, directory):
        """Get all Python files in directory"""
        return [f for f in directory.rglob('*.py') if f.is_file()]

    def analyze_source_file(self, filepath):
        """Analyze a source file to find classes and functions"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=filepath)
        
        functions = set()
        classes = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.add(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.add(node.name)
        
        relative_path = str(filepath.relative_to(self.source_dir.parent))
        line_count = len(content.splitlines())
        
        return {
            'path': relative_path,
            'functions': functions,
            'classes': classes,
            'lines': line_count,
        }

    def analyze_test_file(self, filepath):
        """Analyze a test file to find what it tests"""
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=filepath)
        
        tested_functions = set()
        tested_classes = set()
        
        # Look for test paths and imports
        source_module = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_part = alias.name.split('.')
                    if 'python_task_queue' in module_part:
                        potential_source = '.'.join(module_part)
                        source_module = potential_source
            elif isinstance(node, ast.ImportFrom):
                if node.module and 'python_task_queue' in node.module:
                    source_module = node.module
        
        # Find test functions and what they might test
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                # Extract potential tested function/class names from test function name
                test_name = node.name[5:]  # Remove 'test_' prefix
                parts = re.split('[_-]', test_name)
                for part in parts:
                    if len(part) > 2:  # Ignore small words
                        tested_functions.add(part.lower())
        
        # Look for class name references in test file
        content_lower = content.lower()
        class_patterns = re.findall(r'\b([A-Z][a-zA-Z]+)\b', content)
        for pattern in class_patterns:
            if len(pattern) > 2:
                tested_classes.add(pattern)
        
        return {
            'path': str(filepath.relative_to(self.test_dir.parent)),
            'tested_functions': tested_functions,
            'tested_classes': tested_classes,
            'source_module': source_module,
        }

    def estimate_coverage(self):
        """Estimate coverage based on test and source analysis"""
        # Parse all source files
        for filepath in self.get_all_python_files(self.source_dir):
            if '__pycache__' not in str(filepath:
                result = self.analyze_source_file(filepath)
                self.source_files[result['path']] = result
                module_name = result['path'].replace('/', '.')[:-3]  # Remove .py
                self.coverage_map[module_name]['functions'] = result['functions']
                self.coverage_map[module_name]['classes'] = result['classes']
                self.coverage_map[module_name]['lines'] = result['lines']
        
        # Parse all test files
        for filepath in self.get_all_python_files(self.test_dir):
            if '__pycache__' not in str(filepath and '__init__' not in str(filepath):
                result = self.analyze_test_file(filepath)
                self.test_files[result['path']] = result
                
                # Map tests to source modules
                if result['source_module']:
                    module_name = result['source_module']
                    if module_name in self.coverage_map:
                        self.coverage_map[module_name]['tested_functions'].update(result['tested_functions'])
                        self.coverage_map[module_name]['tested_classes'].update(result['tested_classes'])

    def print_coverage_report(self):
        """Print a coverage report"""
        print("="*70)
        print("MANUAL COVERAGE ANALYSIS REPORT")
        print("="*70)
        print()
        
        total_lines = 0
        total_functions = 0
        total_tested_functions = 0
        
        # Sort modules by name
        modules = sorted(self.coverage_map.keys())
        
        print(f"{'Module':<60} {'Lines':>8} {'Functions':>12} {'Coverage':>10}")
        print("-"*70)
        
        for module in modules:
            data = self.coverage_map[module]
            lines = data['lines']
            functions = data['functions']
            tested = data['tested_functions']
            
            total_lines += lines
            total_functions += len(functions)
            total_tested_functions += len(tested)
            
            # Estimate coverage percentage
            if len(functions) > 0:
                cov_pct = min(100, (len(tested) / len(functions)) * 100)
                cov_str = f"{cov_pct:.1f}%"
                status = "✓" if cov_pct >= 80 else "✗"
            else:
                cov_pct = 0
                cov_str = "N/A"
                status = "?"
            
            # Skip __init__ and very small files
            if '__init__' in module or lines < 10:
                continue
            
            print(f"{status} {module:<58} {lines:>8} {len(functions):>5}/{len(tested):<5} {cov_str:>10}")
        
        print("-"*70)
        
        # Overall coverage
        if total_functions > 0:
            overall_cov = (total_tested_functions / total_functions) * 100
        else:
            overall_cov = 0
        
        print(f"{'TOTAL':<60} {total_lines:>8} {total_functions:>5}/{total_tested_functions:<5} {overall_cov:.1f}%")
        print()
        
        if overall_cov >= 80:
            print("✓ OVERALL COVERAGE MEETS 80% THRESHOLD")
        else:
            print("✗ OVERALL COVERAGE BELOW 80% THRESHOLD")
            print()
            print("Modules with low coverage:")
            for module in modules:
                data = self.coverage_map[module]
                if len(data['functions']) > 0:
                    cov_pct = (len(data['tested_functions']) / len(data['functions'])) * 100
                    if cov_pct < 80:
                        print(f"  - {module}: {cov_pct:.1f}%")
                        if data['functions'] - data['tested_functions']:
                            untested = data['functions'] - data['tested_functions']
                            print(f"    Untested functions: {', '.join(sorted(untested))}")
        
        print()
        print("="*70)
        print("LEGACY TEST FILES:")
        print("="*70)
        for test_file in sorted(self.test_files.keys()):
            print(f"  ✓ {test_file}")
        
        print()
        print("="*70)
        print("SOURCE FILES:")
        print("="*70)
        for source_file in sorted(self.source_files.keys()):
            print(f"  - {source_file} ({self.source_files[source_file]['lines']} lines)")


def main():
    # Get directories
    script_dir = Path(__file__).parent
    source_dir = script_dir / "python_task_queue"
    test_dir = script_dir / "tests"
    
    if not source_dir.exists():
        print(f"Error: Source directory not found: {source_dir}")
        return 1
    
    if not test_dir.exists():
        print(f"Error: Test directory not found: {test_dir}")
        return 1
    
    # Run analyzer
    analyzer = CoverageAnalyzer(source_dir, test_dir)
    analyzer.estimate_coverage()
    analyzer.print_coverage_report()
    
    return 0


if __name__ == "__main__":
    exit(main())