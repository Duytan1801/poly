#!/usr/bin/env python3
"""
Quick Start Example - Unified Insider Detection

Run with: uv run python -X gil=0 examples/quick_start.py
"""

import logging
from poly.unified_insider_detector import (
    UnifiedInsiderDetector,
    quick_scan,
    find_insiders,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def example_1_quick_scan():
    """Example 1: Quick scan of top traders"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Quick Scan (Fast Mode)")
    print("="*80)
    
    # Fast scan of top 50 traders
    results = quick_scan(limit=50, mode="fast")
    
    print(f"\nScanned {len(results)} traders")
    print(f"High-risk: {len([r for r in results if r['risk_score'] >= 5.0])}")
    
    # Show top 5
    print("\nTop 5 by risk score:")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. {r['address'][:10]}... | "
              f"Risk: {r['risk_score']:.1f} | "
              f"{r['level']} | "
              f"{r['profile_type']}")


def example_2_find_insiders():
    """Example 2: Find high-risk insiders"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Find Insiders (Hybrid Mode)")
    print("="*80)
    
    # Find insiders with hybrid mode
    insiders = find_insiders(limit=100, threshold=5.0)
    
    print(f"\nFound {len(insiders)} high-risk traders")
    
    # Group by level
    critical = [r for r in insiders if r['level'] == 'CRITICAL']
    high = [r for r in insiders if r['level'] == 'HIGH']
    
    print(f"  CRITICAL: {len(critical)}")
    print(f"  HIGH: {len(high)}")
    
    if critical:
        print("\nCRITICAL traders:")
        for r in critical[:3]:
            print(f"  🚨 {r['address'][:10]}... | "
                  f"Risk: {r['risk_score']:.1f} | "
                  f"PnL: ${r['leaderboard_pnl']:,.0f}")


def example_3_custom_analysis():
    """Example 3: Custom analysis with configuration"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Custom Analysis")
    print("="*80)
    
    # Initialize detector
    detector = UnifiedInsiderDetector()
    
    try:
        # Analyze top 30 traders in hybrid mode
        results = detector.analyze_top_traders(limit=30, mode="hybrid")
        
        # Filter by custom threshold
        high_risk = detector.filter_high_risk(results, threshold=6.0)
        
        print(f"\nAnalyzed {len(results)} traders")
        print(f"High-risk (>= 6.0): {len(high_risk)}")
        
        # Export to different formats
        print("\nExporting results...")
        
        # As dictionary
        data = detector.export_results(high_risk, format="dict")
        print(f"  Dict: {len(data)} records")
        
        # As Polars DataFrame
        df = detector.export_results(high_risk, format="polars")
        print(f"  Polars: {df.shape[0]} rows x {df.shape[1]} columns")
        
        # Show summary statistics
        if not df.is_empty():
            print("\nSummary Statistics:")
            print(f"  Avg Risk Score: {df['risk_score'].mean():.2f}")
            print(f"  Max Risk Score: {df['risk_score'].max():.2f}")
            print(f"  Avg PnL: ${df['leaderboard_pnl'].mean():,.0f}")
            
    finally:
        detector.close()


def example_4_batch_addresses():
    """Example 4: Analyze specific addresses"""
    print("\n" + "="*80)
    print("EXAMPLE 4: Batch Address Analysis")
    print("="*80)
    
    # Example addresses (replace with real ones)
    addresses = [
        "0x0000000000000000000000000000000000000001",
        "0x0000000000000000000000000000000000000002",
        "0x0000000000000000000000000000000000000003",
    ]
    
    detector = UnifiedInsiderDetector()
    
    try:
        # Analyze specific addresses
        results = detector.analyze_traders(addresses, mode="fast")
        
        print(f"\nAnalyzed {len(results)} addresses")
        
        for profile in results:
            if profile.in_leaderboard:
                print(f"\n{profile.address[:10]}...")
                print(f"  Risk Score: {profile.risk_score:.1f}")
                print(f"  Level: {profile.level}")
                print(f"  PnL: ${profile.leaderboard_pnl:,.0f}")
                print(f"  Rank: #{profile.leaderboard_rank}")
            else:
                print(f"\n{profile.address[:10]}... - Not in leaderboard")
                
    finally:
        detector.close()


def main():
    """Run all examples"""
    print("\n" + "="*80)
    print("UNIFIED INSIDER DETECTION - QUICK START EXAMPLES")
    print("Python 3.14 Free-Threaded Mode")
    print("="*80)
    
    try:
        # Run examples
        example_1_quick_scan()
        example_2_find_insiders()
        example_3_custom_analysis()
        
        # Uncomment to test batch analysis
        # example_4_batch_addresses()
        
        print("\n" + "="*80)
        print("ALL EXAMPLES COMPLETED!")
        print("="*80)
        print("\nNext Steps:")
        print("  1. Replace example addresses with real trader addresses")
        print("  2. Adjust thresholds and limits for your use case")
        print("  3. Integrate into your monitoring pipeline")
        print("  4. Set up caching for production use")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()