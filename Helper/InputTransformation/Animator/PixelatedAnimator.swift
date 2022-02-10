//
// --------------------------------------------------------------------------
// PixelatedAnimator.swift
// Created for Mac Mouse Fix (https://github.com/noah-nuebling/mac-mouse-fix)
// Created by Noah Nuebling in 2021
// Licensed under MIT
// --------------------------------------------------------------------------
//

/// PixelatedAnimator will behave just like Animator with these differences:
/// The animationValueDelta values it passes to it's AnimatorCallback are always integers instead of Doubles
/// To achieve this, the internally generated Double deltas are rounded using a subpixelator which always rounds to the next larger integer (a ceilPixelator)
///     Using ceil instead of normal rounding (roundPixelator) will always generate the first non-zero integer delta immediately on the first frame of animation. I hope that will make the animations this produces marginally more responsive. This only works if the first delta is positive not negative. Since we only use this class in Scroll.m where that's the case, this is okay.
/// Integer deltas which are zero won't be passed to the AnimatorCallback
/// Phases kMFAnimationPhaseStart, and kMFAnimationPhaseEnd will be sent to the AnimatorCallback with the first and last non-zero integer deltas respectively.
///     This behaviour will make this animator great for driving our gestureScrollSimulation, where that kind of input is expected.


import Cocoa
import CocoaLumberjackSwift

class PixelatedAnimator: BaseAnimator {
    
    /// Make stuff from superclass unavailable
    
//    @available(*, unavailable)
//    override func start(params: @escaping StartParamCalculationCallback, callback: @escaping AnimatorCallback) {
//        fatalError();
//    }
    
    /// Declare types and vars that superclass doesn't have
    
    typealias PixelatedAnimatorCallback = (_ integerAnimationValueDelta: Int, _ animationTimeDelta: Double, _ phase: MFAnimationPhase) -> ()
    var integerCallback: PixelatedAnimatorCallback?;
//    var subPixelator: SubPixelator = SubPixelator.ceil();
    /// ^ This being a ceil subPixelator only makes sense because we're only using this through Scroll.m and that's only running this with positive value ranges. So the deltas are being rounded up, and we get a delta immediately as soon as the animations starts, which should make scrolling very small distances feel a little more responsive. If we were dealing with negative deltas, we'd want to round them down instead somehow. Or simply use a SubPixelator.round() which works the same in both directions.
    
    var subPixelator: SubPixelator = SubPixelator.biased();
    /// ^ This biased subpixelator should make SubpixelatedAnimator  also work negative value ranges. So it can also be properly used for for momentum scrolling in GestureScrollAnimator.m
    
    /// Declare new start function
    
    @objc func start(params: @escaping StartParamCalculationCallback,
                     integerCallback: @escaping PixelatedAnimatorCallback) {
        
        self.animatorQueue.async {
        
            /// Get startParams
            
            let p = params(self.animationValueLeft, self.isRunning_Sync, self.animationCurve)
            
            /// Do nothing if doStart == false
            
            if let doStart = p["doStart"] as? Bool {
                if doStart == false {
                    return
                }
            }
            
            /// Debug
            
            let deltaLeftBefore = self.animationValueLeft;
            
            /// Start animator
            
            super.startWithUntypedCallback_Unsafe(duration: p["duration"] as! Double, value: p["vector"] as! Double, animationCurve: p["curve"] as! AnimationCurve, callback: integerCallback)
        
            /// Debug
            
            DDLogDebug("\nStarted PixelatedAnimator with phase: \(self.animationPhase.rawValue), lastPhase: \(self.lastAnimationPhase.rawValue), deltaLeftDiff: \(self.animationValueLeft - deltaLeftBefore), oldDeltaLeft: \(deltaLeftBefore), newDeltaLeft: \(self.animationValueLeft)")
            
            /// Extend start animator method
            
            if self.animationPhase == kMFAnimationPhaseStart {
                self.subPixelator.reset()
            }
            
        }
    }
    
    /// Debug vars
    
    internal var summedIntegerAnimationValueDelta: Int = 0;
    
    /// Hook into superclasses' displayLinkCallback()
    
    override func subclassHook(_ untypedCallback: Any, _ animationValueDelta: Double, _ animationTimeDelta: CFTimeInterval) {
        /// This hooks into displayLinkCallback() in Animator.swift. Look at that for context.
        
        /// Guard callback type
        
        guard let callback = untypedCallback as? PixelatedAnimatorCallback else {
            fatalError("Invalid state - callback is not type PixelatedAnimatorCallback")
        }
        
        /// Get subpixelated animationValueDelta
        
        let integerAnimationValueDelta: Int = Int(self.subPixelator.intDelta(withDoubleDelta: animationValueDelta));
        
        DDLogDebug("AnimationValue now: \(integerAnimationValueDelta)");
        
        if (integerAnimationValueDelta == 0) {
            /// Skip this frames callback and don't update animationPhase from `start` to `continue` if integerValueDelta is 0
            
            /// Debug
            
            DDLogDebug("\nSkipped PixelatedAnimator callback due to 0 delta. phase: \(self.animationPhase.rawValue), lastPhase: \(self.lastAnimationPhase.rawValue)")
            
            /// Validate
            
            if (self.animationPhase == kMFAnimationPhaseEnd || self.animationPhase == kMFAnimationPhaseStartAndEnd) {
                /// This should never happen.
                /// When driving momentumScroll we expect all deltas to be non-zero. I think things will break if we return 0 here. Not totally sure though.
                /// Thoughts on how to prevent this bug:
                ///     Phase can be set to kMFAnimationPhaseEnd in two places.
                ///     1. In Animator.swift > displayLinkCallback(), when the current time is beyond the animationTimeInterval.
                ///     2. Here in PixelatedAnimator.swift > subclassHook(), when processing a non-zero integerDelta, and finding that all the animationValue that's left won't lead to another integer delta (so when the animationValueLeft is smaller than 1)
                ///     -> 2. Should always occur before 1. can occur from my understanding. (That's what this assertion is testing) This will ensure that the delta with phase kMFAnimationPhaseEnd would always be sent and would always contain a non-zero delta.
                
                DDLogError("Integer delta is 0 on final PixelatedAnimator callback. This should never happen.")
                assert(false)
                
                /// Post a value delta of 1 as a fallback so that things don't break as bad if this happens
                callback(1, animationTimeDelta, self.animationPhase)
            }
            
        } else {
            
            /// Update phase to `end` if this was the last int delta
            
            let currentAnimationValueLeft = self.animationValueLeft - animationValueDelta;
            /// ^ We don't use self.animationValueLeft directly, because it's a computed property derived from self.lastAnimationValue which is only updated at the end of displayLinkCallback() - after it calls subclassHook() (which is this function).
            let intAnimationValueLeft = subPixelator.peekIntDelta(withDoubleDelta: currentAnimationValueLeft);
//            if intAnimationValueLeft <= 0 { /// This wouldn't work if the value interval is negative, right? So we're using == 0 instead
            if intAnimationValueLeft == 0 {
                self.animationPhase = kMFAnimationPhaseEnd;
            }
            
            /// Debug
            
            DDLogDebug("AnimationValue prediction: \(intAnimationValueLeft)");
            
            /// Update phase to `startAndEnd` if appropriate
            ///     appropriate -> open if this event was first _and_  last event of animation
            ///     This has a copy in superclass. Update that it when you change this.
            
            if (animationPhase == kMFAnimationPhaseEnd /// This is last event of the animation
                    && lastAnimationPhase == kMFAnimationPhaseNone) { /// This is also the first event of the animation
                animationPhase = kMFAnimationPhaseStartAndEnd;
            }
            
            /// Debug
            
            if animationPhase == kMFAnimationPhaseStart || animationPhase == kMFAnimationPhaseRunningStart || animationPhase == kMFAnimationPhaseStartAndEnd {
                summedIntegerAnimationValueDelta = 0
            }
            self.summedIntegerAnimationValueDelta += integerAnimationValueDelta
            
//            DDLogDebug("""
//PxAnim - intValueDelta: \(integerAnimationValueDelta), intValueLeft: \(intAnimationValueLeft), animationPhase: \(self.animationPhase.rawValue),     value: \(lastAnimationValue + animationValueDelta) intValue: \(summedIntegerAnimationValueDelta), intervalLength: \(self.animationValueInterval.length),     valueDelta: \(animationValueDelta), accEoundingErr: \(subPixelator.accumulatedRoundingError), currentnimationValueLeft: \(currentAnimationValueLeft),
//""")
//            DDLogDebug("PxAnim - intValueDelta: \(integerAnimationValueDelta)")
            
            if summedIntegerAnimationValueDelta >= Int(self.animationValueInterval.length) {
//                assert(animationPhase == kMFAnimationPhaseEnd)
            }
            
            /// Call callback
            
            callback(integerAnimationValueDelta, animationTimeDelta, self.animationPhase)
            
            /// Debug
            
            DDLogDebug("\nPixelatedAnimator callback with delta: \(integerAnimationValueDelta), phase: \(self.animationPhase.rawValue), lastPhase: \(self.lastAnimationPhase.rawValue)")
            
            /// Update `last` phase
            
            self.lastAnimationPhase = self.animationPhase
            
            /// Update phase to `continue` if phase is `start`
            ///     This has a copy in superclass. Update that it when you change this.
            
            switch self.animationPhase {
            case kMFAnimationPhaseStart, kMFAnimationPhaseRunningStart: self.animationPhase = kMFAnimationPhaseContinue
            default: break }
            
        }
    }
    
}