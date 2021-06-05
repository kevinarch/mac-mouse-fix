//
// --------------------------------------------------------------------------
// Math.swift
// Created for Mac Mouse Fix (https://github.com/noah-nuebling/mac-mouse-fix)
// Created by Noah Nuebling in 2021
// Licensed under MIT
// --------------------------------------------------------------------------
//

import Cocoa

@objc class Math: NSObject {

    /// Source https://blog.plover.com/math/choose.html
    @objc class func choose(_ nArg: Int, _ k: Int) -> Int {
        var n: Int = nArg
        var r: Int = 1
        
        if k > n { return 0 }
        
        for d in 1...k {
            r *= n
            r /= d
            n -= 1
        }
        return r;
    }
    
    @objc class func scale(value: Double, fromRange sourceRange: ContinuousRange, toRange targetRange: ContinuousRange) -> Double {
        
        assert(sourceRange.contains(value))
        
        // Normalize value (between 0 and 1)
    
        let normalizedValue: Double = (value - sourceRange.lower) / sourceRange.length
        
        // Scale normalized value to targetRange
        
        return normalizedValue * targetRange.length + targetRange.lower
    }
}

@objc class ContinuousRange: NSObject {
    
    let location: Double
    let length: Double
    
    var lower: Double {
        location
    }
    var upper: Double {
        location + length
    }
    
    class func normalRange() -> ContinuousRange {
        return self.init(lower: 0.0, upper: 1.0)
    }
    
    required init(lower: Double, upper: Double) {
        self.location = lower
        self.length = upper - lower
    }
    
    init(location: Double, length: Double) {
        self.location = location
        self.length = length
    }
    
    func contains(_ value: Double) -> Bool {
        return location <= value && value <= upper
    }
    
}