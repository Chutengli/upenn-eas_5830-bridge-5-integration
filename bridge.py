from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]



def sign_and_send(contract, function_name, w3, warden_private_key, argdict):
    try:
        warden_account = w3.eth.account.from_key(warden_private_key)
        nonce = w3.eth.get_transaction_count(warden_account.address)
        contract_func = getattr(contract.functions, function_name)
        tx = contract_func(**argdict).build_transaction({
            'nonce': nonce,
            'gasPrice': w3.eth.gas_price,
            'from': warden_account.address,
            'gas': 10 ** 6
        })
        signed_tx = w3.eth.account.sign_transaction(tx, warden_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"Transaction sent: {tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status:
            print(f"Transaction confirmed at block {receipt.blockNumber}")
        else:
            print(f"Transaction failed")
        return receipt
    except Exception as e:
        print(f"Error in sign_and_send: {e}")
        import traceback
        traceback.print_exc()
        return None


def scan_blocks(chain, contract_info="contract_info.json"):
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
    try:
        with open(contract_info, 'r') as f:
            contracts = json.load(f)
    except Exception as e:
        print(f"Failed to read contract info: {e}")
        return 0
    
    warden_private_key = contracts['warden']['private_key']
    
    if chain == 'source':
        source_w3 = connect_to('source')
        destination_w3 = connect_to('destination')
        
        source_contract_data = contracts['source']
        destination_contract_data = contracts['destination']
        
        source_contract = source_w3.eth.contract(
            abi=source_contract_data['abi'],
            address=source_contract_data['address']
        )
        destination_contract = destination_w3.eth.contract(
            abi=destination_contract_data['abi'],
            address=destination_contract_data['address']
        )
        end_block = source_w3.eth.get_block_number()
        start_block = max(0, end_block - 5)
        
        
        try:
            event_filter = source_contract.events.Deposit.create_filter(
                from_block=start_block,
                to_block=end_block
            )
            events = event_filter.get_all_entries()
            
            for evt in events:
                token = evt.args['token']
                recipient = evt.args['recipient']
                amount = evt.args['amount']
                
                try:
                    sign_and_send(
                        destination_contract,
                        'wrap',
                        destination_w3,
                        warden_private_key,
                        {
                            '_underlying_token': token,
                            '_recipient': recipient,
                            '_amount': amount
                        }
                    )
                except Exception as e:
                    print(f"Error calling wrap: {e}")
                    
        except Exception as e:
            print(f"Error scanning for Deposit events: {e}")
    
    elif chain == 'destination':
        source_w3 = connect_to('source')
        destination_w3 = connect_to('destination')
        
        source_contract_data = contracts['source']
        destination_contract_data = contracts['destination']
        
        source_contract = source_w3.eth.contract(
            abi=source_contract_data['abi'],
            address=source_contract_data['address']
        )
        destination_contract = destination_w3.eth.contract(
            abi=destination_contract_data['abi'],
            address=destination_contract_data['address']
        )
        
        end_block = destination_w3.eth.get_block_number()
        start_block = max(0, end_block - 5)
                
        try:
            event_filter = destination_contract.events.Unwrap.create_filter(
                from_block=start_block,
                to_block=end_block
            )
            events = event_filter.get_all_entries()
            
            for evt in events:
                underlying_token = evt.args['underlying_token']
                wrapped_token = evt.args['wrapped_token']
                to = evt.args['to']
                amount = evt.args['amount']
                                
                try:
                    sign_and_send(
                        source_contract,
                        'withdraw',
                        source_w3,
                        warden_private_key,
                        {
                            '_token': underlying_token,
                            '_recipient': to,
                            '_amount': amount
                        }
                    )
                except Exception as e:
                    print(f"Error calling withdraw: {e}")
                    
        except Exception as e:
            print(f"Error scanning for Unwrap events: {e}")
    
    return 1
