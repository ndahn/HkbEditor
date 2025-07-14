# Just a rough outline of how the XML is structured. This is not coffee script, 
# but vscode was able to do some nice syntax highlighting this way

-> object240 hkbStateMachine
    - name: "Master_SM"
    - variableBindingSet: object309
    - states[24]: 
        - ...
        - object330
        - ...

-> object330 hkbStateMachine::StateInfo
    - name: "NewJump"
    - generator: object374

-> object374 hkbScriptGenerator
    - name: "NewJump Script"
    - child: object500
    - onActivateScript: "Jump_Activate()"
    - onPreUpdateScript: "Jump_Update()"
    - onGenerateScript: ""
    - onHandleEventScript: ""
    - onDeactivateScript: ""

-> object500 hkbLayerGenerator
    - name: "NewJump LayerGenerator"
    - layers[3]:
        - object736
        - object737
        - object738

-> object736 hkbLayer
    - generator: object1096

-> object1096 hkbStateMachine
    - name: "NewJump StateMachine"
    - wildcardTransitions: object2057
    - generators[20]:
        - ...
        - object2039
        - ...

# --------------------------------

-> object2039 hkbStateMachine::StateInfo 
	- name: "Jump_F"
	- transitions: object2930
	- generator: object2931
	- stateId: 56


	-> object2930 hkbStateMachine::TransitionInfoArray
		- transitions: array[1] hkbStateMachine::TransitionInfo
			- <noid> hkbStateMachine::TransitionInfo
				- transition: object7434
				- condition: object0
				- eventId: 509 (eventNames -> W_Stealth_to_Idle)
				- toStateId: 58 (SM object1096 -> StateInfo object2041 ("Jump_Loop"))

		-> object7434 CustomTransitionEffect
			- name: "Jump_F_to_Jump_Loop"
			- selfTransitionMode: 0 (SELF_TRANSITION_MODE_CONTINUE_IF_CYCLIC_BLEND_IF_ACYCLIC)
			- duration: 0.5


	-> object2931 hkbLayerGenerator
		- name: "Jump_F LayerGenerator"
		- layers: array[2]
			- object7435
			- object7436

		-> object7435 hkbLayer
			- variableBindingSet: object10803
			- generator: object10804
			- blendingControlData: 
				- <hkbEventDrivenBlendingObject>
					- onEventId: 569
					
			-> object10804 hkbManualSelectorGenerator
				- name: "Jump_F HandCondition Selector"
				- variableBindingSet: object15244
				- generators[4]: 
					- object15245
					- object15246
					- object15247
					- object15248
					
				-> object15244 hkbVariableBindingSet
					- bindings[1]:
						- <hkbVariableBindingSet::Binding>
							- memberPath: "selectedGeneratorIndex"
							- variableIndex: 214 (->variableNames[214] = "JumpAttack_HandCondition")
				
				-> object15245 hkbManualSelectorGenerator
					- name: "Jump_F Selector_N-HAttack_Right"
					- variableBindingSet: object19103
					- generators[4]:
						- object19104
						- object19105
						- object19106
						- object19107
				
				-> object15246 hkbManualSelectorGenerator
					- name: "Jump_F Selector_N-HAttack_Both"
					- variableBindingSet: object19108
					- generators[2]: 
						- object19109
						- object19110
				
				-> object15247 hkbManualSelectorGenerator
					- name: "Jump_F Selector_Magic_Left"
					- variableBindingSet: object19111
					- generators[3]:
						- object19112
						- object19113
						- object19114
					- generatorChangedTransitionEffect: object10909
				
				-> object15248 hkbManualSelectorGenerator
					- name: "Jump_F Selector_N-HAttack_BothLeft"
					- variableBindingSet: object19115
					- generators[2]: 
						- object19116
						- object19117
				
					
		-> object7436 hkbLayer
			- variableBindingSet: object10805
			- generator: object10806
			
			-> object10805 hkbVariableBindingSet
				- bindings[1]:
					- <noid> hkbVariableBindingSet::Binding
						- memberPath: "blendingControlData/weight"
						- variableIndex: 211

			-> object10806 hkbManualSelectorGenerator
				- name: "Jump_F_Direction_MSG"
				- variableBindingSet: object15249
				- generators[4]:
					- object15250
					- object15251
					- object15252
					- object15253

				-> object15250 CustomManualSelectorGenerator
					- name: "Jump_F_Direction_Front_CMSG"
					- variableBindingSet: object19118
					- animId: 202020
					- enableScript: true
					- enableTae: true
					- generators[4]:
						- object19119
						- object19120
						- object19121
						- object19122
						- object19123
						- object19124
						- object19125
						- object19126
						- object19127

					-> object19118 hkbVariableBindingSet
						- bindings[1]:
							- <noid> hkbVariableBindingSet::Binding
								- memberPath: "enableTae"
								- variableIndex: 274

					-> object19119 hkbClipGenerator
						- name: "a000_202020_hkx_AutoSet_00"
						- animationName: "a000_202020"
					
					-> object19120 hkbClipGenerator
						- name: "a002_202020_hkx_AutoSet_00"
						- animationName: "a002_202020"
					
					-> object19121 hkbClipGenerator
						- name: "a003_202020_hkx_AutoSet_00"
						- animationName: "a003_202020"
					
					-> object19122 hkbClipGenerator
						- name: "a010_202020_hkx_AutoSet_00"
						- animationName: "a010_202020"
					
					-> object19123 hkbClipGenerator
						- name: "a012_202020_hkx_AutoSet_00"
						- animationName: "a012_202020"
					
					-> object19124 hkbClipGenerator
						- name: "a013_202020_hkx_AutoSet_00"
						- animationName: "a013_202020"
					
					-> object19125 hkbClipGenerator
						- name: "a014_202020_hkx_AutoSet_00"
						- animationName: "a014_202020"
					
					-> object19126 hkbClipGenerator
						- name: "a015_202020_hkx_AutoSet_00"
						- animationName: "a015_202020"
					
					-> object19127 hkbClipGenerator
						- name: "a016_202020_hkx_AutoSet_00"
						- animationName: "a016_202020"
					
				-> object15251 CustomManualSelectorGenerator
                    ...