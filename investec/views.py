import pandas as pd
import re
import os
from datetime import datetime
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.db import transaction
from django.utils.dateparse import parse_date
from decimal import Decimal, InvalidOperation

from .models import InvestecJseTransaction, InvestecJsePortfolio, InvestecJseShareNameMapping
from .serializers import InvestecJseTransactionSerializer, InvestecJsePortfolioSerializer, InvestecJseShareNameMappingSerializer



# ------------------------------------------------
# Import Transaction Data
# ------------------------------------------------

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def excel_upload_view(request):
    """
    API endpoint to upload Excel file and import transactions.
    
    Accepts POST request with 'file' field containing Excel file.
    Returns import statistics and any errors encountered.
    """
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided. Please upload an Excel file.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    uploaded_file = request.FILES['file']
    
    # Validate file extension
    if not uploaded_file.name.endswith(('.xlsx', '.xls')):
        return Response(
            {'error': 'Invalid file format. Please upload an Excel file (.xlsx or .xls).'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Read Excel file - try to find header row
        # First, read without header to inspect structure
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        # Find header row (look for row containing 'Date' and 'Account Number')
        header_row = None
        for idx, row in df_raw.iterrows():
            row_str = ' '.join([str(val).lower() for val in row.values if pd.notna(val)])
            if 'date' in row_str and 'account' in row_str:
                header_row = idx
                break
        
        # If header row found, read with that row as header
        if header_row is not None:
            # Read with header_row as column names - pandas automatically starts data from next row
            df = pd.read_excel(uploaded_file, header=header_row)
        else:
            # Fallback: read normally and try to detect columns
            df = pd.read_excel(uploaded_file)
        
        # Normalize column names (remove spaces, convert to lowercase)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('-', '_')
        
        # Map common column name variations to model fields
        column_mapping = {
            'date': ['date', 'transaction_date', 'trade_date'],
            'account_number': ['account_number', 'account', 'account_no', 'accountnum'],
            'description': ['description', 'desc', 'details'],
            'share_name': ['share_name', 'sharename', 'stock_name', 'stock', 'instrument', 'security', 'share_name'],
            'type': ['type', 'action', 'transaction_type', 'transaction', 'side'],
            'quantity': ['quantity', 'qty', 'shares', 'units'],
            'value': ['value', 'amount', 'price', 'total', 'transaction_value'],
        }
        
        # Find actual column names in the dataframe
        actual_columns = {}
        for model_field, possible_names in column_mapping.items():
            for possible_name in possible_names:
                if possible_name in df.columns:
                    actual_columns[model_field] = possible_name
                    break
        
        # Check if all required columns are found (type can be extracted from description)
        required_fields = ['date', 'account_number', 'description', 'share_name', 'quantity', 'value']
        missing_fields = [field for field in required_fields if field not in actual_columns]
        
        if missing_fields:
            return Response(
                {
                    'error': f'Missing required columns: {", ".join(missing_fields)}',
                    'available_columns': list(df.columns),
                    'suggestion': 'Please ensure your Excel file contains columns matching: date, account_number, description, share_name, quantity, value'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Extract date range from filename (format: TransactionHistory-All-YYYYMMDD-YYYYMMDD.xlsx)
        from_date = None
        to_date = None
        
        filename = uploaded_file.name
        # Try to extract dates from filename pattern: ...-YYYYMMDD-YYYYMMDD...
        date_pattern = re.search(r'(\d{8})-(\d{8})', filename)
        if date_pattern:
            try:
                from_date_str = date_pattern.group(1)
                to_date_str = date_pattern.group(2)
                from_date = pd.to_datetime(from_date_str, format='%Y%m%d').date()
                to_date = pd.to_datetime(to_date_str, format='%Y%m%d').date()
            except:
                pass
        
        # If not found in filename, try to find dates in the Excel file itself
        if from_date is None or to_date is None:
            # Look for "From" and "To" date patterns in the raw data
            for idx, row in df_raw.iterrows():
                row_str = ' '.join([str(val) for val in row.values if pd.notna(val)])
                row_lower = row_str.lower()
                
                # Look for "from date" or "to date" patterns
                if 'from' in row_lower and 'date' in row_lower:
                    # Try to extract date from this row
                    for cell_val in row.values:
                        if pd.notna(cell_val):
                            cell_str = str(cell_val).strip()
                            # Try various date formats
                            for date_format in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y%m%d', '%d %B %Y', '%d %b %Y']:
                                try:
                                    parsed_date = pd.to_datetime(cell_str, format=date_format).date()
                                    if from_date is None:
                                        from_date = parsed_date
                                    elif to_date is None and parsed_date > from_date:
                                        to_date = parsed_date
                                    break
                                except:
                                    try:
                                        parsed_date = pd.to_datetime(cell_str).date()
                                        if from_date is None:
                                            from_date = parsed_date
                                        elif to_date is None and parsed_date > from_date:
                                            to_date = parsed_date
                                        break
                                    except:
                                        continue
                
                if 'to' in row_lower and 'date' in row_lower:
                    # Try to extract date from this row
                    for cell_val in row.values:
                        if pd.notna(cell_val):
                            cell_str = str(cell_val).strip()
                            # Try various date formats
                            for date_format in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y%m%d', '%d %B %Y', '%d %b %Y']:
                                try:
                                    parsed_date = pd.to_datetime(cell_str, format=date_format).date()
                                    if to_date is None or parsed_date > to_date:
                                        to_date = parsed_date
                                    break
                                except:
                                    try:
                                        parsed_date = pd.to_datetime(cell_str).date()
                                        if to_date is None or parsed_date > to_date:
                                            to_date = parsed_date
                                        break
                                    except:
                                        continue
                
                # Stop searching after finding both dates or after checking first 20 rows
                if from_date and to_date or idx > 20:
                    break
        
        # Clear existing transactions only for the date range being uploaded
        if from_date and to_date:
            deleted_count = InvestecJseTransaction.objects.filter(
                date__gte=from_date,
                date__lte=to_date
            ).delete()[0]
        else:
            # If we can't determine the date range, don't delete anything
            # This is safer than deleting all transactions
            deleted_count = 0
        
        # Prepare data for bulk creation
        transactions_to_create = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Parse date
                date_value = row[actual_columns['date']]
                
                # Skip rows with empty date (header rows that might have been included)
                if pd.isna(date_value) or (isinstance(date_value, str) and str(date_value).strip() == ''):
                    continue
                
                # Handle different date formats
                if isinstance(date_value, str):
                    parsed_date = parse_date(date_value)
                    if not parsed_date:
                        # Try pandas to_datetime
                        try:
                            parsed_date = pd.to_datetime(date_value).date()
                        except:
                            errors.append(f'Row {index + 2}: Invalid date format: {date_value}')
                            continue
                elif isinstance(date_value, pd.Timestamp):
                    parsed_date = date_value.date()
                elif hasattr(date_value, 'date'):  # datetime object
                    parsed_date = date_value.date()
                else:
                    # Try to convert to date
                    try:
                        parsed_date = pd.to_datetime(date_value).date()
                    except:
                        errors.append(f'Row {index + 2}: Invalid date format: {date_value}')
                        continue
                
                # Parse quantity
                quantity_value = row[actual_columns['quantity']]
                if pd.isna(quantity_value):
                    errors.append(f'Row {index + 2}: Quantity is missing')
                    continue
                try:
                    quantity = Decimal(str(quantity_value))
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {index + 2}: Invalid quantity value: {quantity_value}')
                    continue
                
                # Get description early to check for dividend patterns
                description_val = row[actual_columns['description']]
                description = str(description_val)[:255] if not pd.isna(description_val) else ''
                
                # For dividends, quantity might be in description
                # Patterns: "DIV. 327 NINETY 1L" -> quantity is 327
                #          "FOREIGN DIV. 3061 BATS" -> quantity is 3061
                #          "DIV. TAX ON 74 NINETY 1L" -> quantity is 74
                #          "SPEC.DIV. 1229 OUTSURE" -> quantity is 1229
                if quantity == 0 and description:
                    description_upper = description.upper()
                    if 'FOREIGN DIV' in description_upper:
                        # Extract quantity from pattern like "FOREIGN DIV. 3061 BATS"
                        foreign_div_match = re.search(r'FOREIGN\s+DIV\.?\s*(\d+)', description, re.IGNORECASE)
                        if foreign_div_match:
                            try:
                                quantity = Decimal(foreign_div_match.group(1))
                            except (InvalidOperation, ValueError):
                                pass  # Keep original quantity if extraction fails
                    elif 'SPEC.DIV' in description_upper or 'SPECIAL DIV' in description_upper or 'SPECIAL DIVIDEND' in description_upper:
                        # Extract quantity from pattern like "SPEC.DIV. 1229 OUTSURE"
                        spec_div_match = re.search(r'SPEC(?:IAL)?\.?\s*DIV(?:IDEND)?\.?\s*(\d+)', description, re.IGNORECASE)
                        if spec_div_match:
                            try:
                                quantity = Decimal(spec_div_match.group(1))
                            except (InvalidOperation, ValueError):
                                pass  # Keep original quantity if extraction fails
                    elif 'DIV. TAX' in description_upper or 'DIVIDEND TAX' in description_upper:
                        # Extract quantity from pattern like "DIV. TAX ON 74 NINETY 1L"
                        div_tax_match = re.search(r'DIV\.?\s*TAX\s+ON\s+(\d+)', description, re.IGNORECASE)
                        if div_tax_match:
                            try:
                                quantity = Decimal(div_tax_match.group(1))
                            except (InvalidOperation, ValueError):
                                pass  # Keep original quantity if extraction fails
                    elif description_upper.startswith('DIV'):
                        # Extract quantity from pattern like "DIV. 327 NINETY 1L"
                        div_match = re.search(r'DIV\.?\s*(\d+)', description, re.IGNORECASE)
                        if div_match:
                            try:
                                quantity = Decimal(div_match.group(1))
                            except (InvalidOperation, ValueError):
                                pass  # Keep original quantity if extraction fails
                
                # Parse value
                value_value = row[actual_columns['value']]
                if pd.isna(value_value):
                    errors.append(f'Row {index + 2}: Value is missing')
                    continue
                try:
                    value = Decimal(str(value_value))
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {index + 2}: Invalid value: {value_value}')
                    continue
                
                # Get other fields
                # Account number - handle both string and numeric values
                account_number_val = row[actual_columns['account_number']]
                if pd.isna(account_number_val):
                    account_number = ''
                else:
                    # Convert to string, handling numeric values
                    account_number = str(int(account_number_val)) if isinstance(account_number_val, (int, float)) else str(account_number_val)
                    account_number = account_number[:50]
                
                # Share name - try to extract from description if missing
                share_name_val = row[actual_columns['share_name']]
                if pd.isna(share_name_val) or str(share_name_val).strip() == '':
                    # Try to extract share name from description
                    if description:
                        description_upper = description.upper()
                        # For foreign dividends: "FOREIGN DIV. 3061 BATS" -> extract "BATS"
                        #                      "FOREIGN DIV. 123 A V I" -> extract "A V I" and convert to "AVI"
                        if 'FOREIGN DIV' in description_upper:
                            # Try to match spaced letters first (e.g., "A V I" -> "AVI")
                            foreign_spaced_match = re.search(r'FOREIGN\s+DIV\.?\s*\d+\s+((?:[A-Z]\s+)+[A-Z])', description, re.IGNORECASE)
                            if foreign_spaced_match:
                                # Remove spaces from spaced letters (e.g., "A V I" -> "AVI")
                                spaced_name = foreign_spaced_match.group(1)
                                share_name = spaced_name.replace(' ', '').upper()[:100]
                            else:
                                # Try regular word pattern
                                foreign_div_share_match = re.search(r'FOREIGN\s+DIV\.?\s*\d+\s+(\w+)', description, re.IGNORECASE)
                                if foreign_div_share_match:
                                    share_name = foreign_div_share_match.group(1).upper()[:100]
                                else:
                                    # Fallback: look for uppercase words after the number
                                    words = description.split()
                                    found_number = False
                                    for word in words:
                                        if word.isdigit():
                                            found_number = True
                                        elif found_number and word.isupper() and len(word) > 2:
                                            share_name = word[:100]
                                            break
                                    else:
                                        share_name = ''
                        # For special dividends: "SPEC.DIV. 1229 OUTSURE" -> extract "OUTSURE"
                        elif 'SPEC.DIV' in description_upper or 'SPECIAL DIV' in description_upper or 'SPECIAL DIVIDEND' in description_upper:
                            # Extract share name from pattern like "SPEC.DIV. 1229 OUTSURE"
                            spec_div_share_match = re.search(r'SPEC(?:IAL)?\.?\s*DIV(?:IDEND)?\.?\s*\d+\s+(\w+)', description, re.IGNORECASE)
                            if spec_div_share_match:
                                share_name = spec_div_share_match.group(1).upper()[:100]
                            else:
                                # Fallback: look for uppercase words after the number
                                words = description.split()
                                found_number = False
                                for word in words:
                                    if word.isdigit():
                                        found_number = True
                                    elif found_number and word.isupper() and len(word) > 2:
                                        share_name = word[:100]
                                        break
                                else:
                                    share_name = ''
                        # For regular dividends: "DIV. 327 NINETY 1L" -> extract "NINETY"
                        #                    "DIV. 446 A V I" -> extract "A V I" and convert to "AVI"
                        #                    "DIV. TAX ON 74 NINETY 1L" -> extract "NINETY"
                        elif description_upper.startswith('DIV'):
                            # Handle "DIV. TAX ON" pattern: "DIV. TAX ON 74 NINETY 1L" -> "NINETY"
                            div_tax_match = re.search(r'DIV\.?\s*TAX\s+ON\s+\d+\s+(\w+)', description, re.IGNORECASE)
                            if div_tax_match:
                                share_name = div_tax_match.group(1).upper()[:100]
                            else:
                                # Try to match spaced letters first (e.g., "A V I" -> "AVI")
                                spaced_letters_match = re.search(r'DIV\.?\s*\d+\s+((?:[A-Z]\s+)+[A-Z])', description, re.IGNORECASE)
                                if spaced_letters_match:
                                    # Remove spaces from spaced letters (e.g., "A V I" -> "AVI")
                                    spaced_name = spaced_letters_match.group(1)
                                    share_name = spaced_name.replace(' ', '').upper()[:100]
                                else:
                                    # Try regular word pattern (e.g., "DIV. 327 NINETY 1L" -> "NINETY")
                                    div_share_match = re.search(r'DIV\.?\s*\d+\s+(\w+)', description, re.IGNORECASE)
                                    if div_share_match:
                                        share_name = div_share_match.group(1).upper()[:100]
                                    else:
                                        # Fallback: look for uppercase words
                                        words = description.split()
                                        for word in words:
                                            if word.isupper() and len(word) > 2 and word not in ['DIV', 'DIVIDEND', 'FOREIGN', 'TAX', 'ON']:
                                                share_name = word[:100]
                                                break
                                        else:
                                            share_name = ''
                        else:
                            # For other transactions: "Buy 179 NEDBANK" -> "NEDBANK"
                            words = description.split()
                            for word in reversed(words):  # Check from end, as share name is usually at the end
                                if word.isupper() and len(word) > 2:
                                    share_name = word[:100]
                                    break
                            else:
                                share_name = ''  # Couldn't extract, use empty
                    else:
                        share_name = ''
                else:
                    share_name = str(share_name_val)[:100]
                
                # Extract type from description if not a separate column
                if 'type' in actual_columns:
                    transaction_type = str(row[actual_columns['type']])[:50] if not pd.isna(row[actual_columns['type']]) else ''
                else:
                    # Try to extract type from description (e.g., "Buy 179 NEDBANK" -> "Buy")
                    transaction_type = ''
                    if description:
                        description_upper = description.upper()
                        # Account-related transactions (no share code)
                        if 'FEE' in description_upper or 'QUARTERLY ADMIN FEE' in description_upper:
                            transaction_type = 'Fee'
                        elif 'BROKER' in description_upper:
                            transaction_type = 'Broker Fee'
                        elif 'VAT' in description_upper:
                            transaction_type = 'VAT'
                        elif 'CAP.REDUC' in description_upper or 'CAPITAL REDUCTION' in description_upper:
                            transaction_type = 'Capital Reduction'
                        elif 'INTER A/C TRF' in description_upper or 'INTER ACCOUNT TRANSFER' in description_upper:
                            transaction_type = 'Inter Account Transfer'
                        elif 'TRF' in description_upper and ('TO' in description_upper or 'FROM' in description_upper):
                            # Handle "TRF FROM TRADING TO INCOME", "TRF INCOME TO TRADING", and similar transfer patterns
                            transaction_type = 'Transfer'
                        elif 'TRANSFER FROM' in description_upper or 'TRANSFER TO' in description_upper:
                            # Handle "TRANSFER FROM" and "TRANSFER TO" patterns
                            transaction_type = 'Transfer'
                        elif 'INVESTEC BANK' in description_upper or 'BANK TRANSFER' in description_upper:
                            transaction_type = 'Bank Transfer'
                        elif 'INTEREST' in description_upper:
                            transaction_type = 'Interest'
                        # Check for account number pattern: "10011910139 - MC DIPPENAAR" -> Transfer
                        elif re.match(r'^\d+\s*-\s*[A-Z\s]+$', description, re.IGNORECASE):
                            transaction_type = 'Transfer'
                        # Share-related transactions
                        elif 'FOREIGN DIV' in description_upper:
                            transaction_type = 'Foreign Dividend'
                        elif 'DIV. TAX' in description_upper or 'DIVIDEND TAX' in description_upper:
                            transaction_type = 'Dividend Tax'
                        elif 'SPEC.DIV' in description_upper or 'SPECIAL DIV' in description_upper or 'SPECIAL DIVIDEND' in description_upper:
                            transaction_type = 'Special Dividend'
                        elif description_upper.startswith('BUY'):
                            transaction_type = 'Buy'
                        elif description_upper.startswith('SELL'):
                            transaction_type = 'Sell'
                        elif 'DIV' in description_upper or 'DIVIDEND' in description_upper:
                            transaction_type = 'Dividend'
                        else:
                            # Default: take first word as type
                            transaction_type = description.split()[0][:50] if description.split() else ''
                
                # Validate required fields - account_number is always required
                if not account_number:
                    errors.append(f'Row {index + 2}: Missing required field (account_number)')
                    continue
                
                # Check if this is an account-related transaction (no share code)
                # These include: FEE, BROKER, VAT, CAP.REDUC, INTEREST, Bank Transfer, QUARTERLY ADMIN FEE, Transfers
                is_account_transaction = False
                if description:
                    desc_upper = description.upper()
                    account_keywords = ['FEE', 'BROKER', 'VAT', 'CAP.REDUC', 'CAPITAL REDUCTION', 
                                       'BANK TRANSFER', 'TRANSFER', 'QUARTERLY ADMIN FEE', 
                                       'INTER A/C TRF', 'INTER ACCOUNT TRANSFER', 'INVESTEC BANK',
                                       'TRF FROM', 'TRF TO', 'TRANSFER FROM', 'TRANSFER TO']
                    is_account_transaction = any(keyword in desc_upper for keyword in account_keywords)
                    
                    # Check for "TRF [something] TO [something]" pattern (e.g., "TRF INCOME TO TRADING")
                    if 'TRF' in desc_upper and 'TO' in desc_upper:
                        is_account_transaction = True
                    # Check for "TRF [something] FROM [something]" pattern
                    if 'TRF' in desc_upper and 'FROM' in desc_upper:
                        is_account_transaction = True
                    
                    # Check for account number pattern: "10011910139 - MC DIPPENAAR"
                    if re.match(r'^\d+\s*-\s*[A-Z\s]+$', description, re.IGNORECASE):
                        is_account_transaction = True
                
                # Ensure account-related types always have blank share_name
                account_types = ['VAT', 'Fee', 'Interest', 'Broker Fee', 'Capital Reduction', 
                                   'Bank Transfer', 'Inter Account Transfer', 'Transfer']
                if transaction_type in account_types:
                    share_name = ''  # Force blank share_name for account-related types
                    is_account_transaction = True
                
                # Special case: Transfer patterns should have no share name
                # Patterns: "TRF FROM TRADING TO INCOME", "TRF INCOME TO TRADING", "TRF TRADING TO INCOME", etc.
                if description:
                    desc_upper_transfer = description.upper()
                    if ('TRF' in desc_upper_transfer and ('TO' in desc_upper_transfer or 'FROM' in desc_upper_transfer)):
                        share_name = ''
                        is_account_transaction = True
                
                # For account-related transactions, allow empty share_name
                # For share transactions, use empty string if share_name is missing (model allows blank)
                if not share_name and not is_account_transaction:
                    share_name = ''  # Empty string for share transactions without share name (model allows blank)
                # If it's an account transaction, share_name remains empty
                
                # Extract value per share from description for Buy/Sell transactions
                value_per_share = None
                value_calculated = None
                if transaction_type in ['Buy', 'Sell'] and description:
                    # Pattern: "at 1,192 Cents" or "at 5000 Cents"
                    price_match = re.search(r'at\s+([\d,]+)\s+Cents', description, re.IGNORECASE)
                    if price_match:
                        price_str = price_match.group(1).replace(',', '')
                        try:
                            # Convert from cents to rands (divide by 100)
                            price_cents = Decimal(price_str)
                            value_per_share = price_cents / Decimal('100')
                            
                            # Calculate value_calculated = value_per_share * quantity
                            value_calculated = value_per_share * quantity
                            
                            # Make negative for Buy transactions
                            if transaction_type == 'Buy':
                                value_calculated = value_calculated * Decimal('-1')
                        except (InvalidOperation, ValueError):
                            pass
                
                transactions_to_create.append(
                    InvestecJseTransaction(
                        date=parsed_date,
                        year=parsed_date.year,
                        month=parsed_date.month,
                        day=parsed_date.day,
                        account_number=account_number,
                        description=description,
                        share_name=share_name,
                        type=transaction_type,
                        quantity=quantity,
                        value=value,
                        value_per_share=value_per_share,
                        value_calculated=value_calculated,
                    )
                )
            except Exception as e:
                errors.append(f'Row {index + 2}: {str(e)}')
                continue
        
        # Bulk create transactions
        created_count = 0
        if transactions_to_create:
            with transaction.atomic():
                created_instances = InvestecJseTransaction.objects.bulk_create(
                    transactions_to_create,
                    ignore_conflicts=False
                )
                created_count = len(created_instances)
        
        # Prepare response
        response_data = {
            'success': True,
            'message': f'Successfully imported {created_count} transactions',
            'deleted_previous': deleted_count,
            'total_rows': len(df),
            'created': created_count,
            'errors': len(errors),
        }
        
        # Add date range information if available
        if from_date and to_date:
            response_data['date_range'] = {
                'from_date': str(from_date),
                'to_date': str(to_date),
            }
            response_data['message'] += f' for date range {from_date} to {to_date}'
        elif from_date:
            response_data['date_range'] = {
                'from_date': str(from_date),
                'to_date': None,
            }
        elif to_date:
            response_data['date_range'] = {
                'from_date': None,
                'to_date': str(to_date),
            }
        
        if errors:
            response_data['error_details'] = errors[:50]  # Limit to first 50 errors
            if len(errors) > 50:
                response_data['error_details'].append(f'... and {len(errors) - 50} more errors')
        
        return Response(response_data, status=status.HTTP_201_CREATED if created_count > 0 else status.HTTP_200_OK)
        
    except pd.errors.EmptyDataError:
        return Response(
            {'error': 'The Excel file is empty.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': f'Error processing file: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def transaction_list_view(request):
    """
    API endpoint to list all Investec transactions.
    
    Supports query parameters:
    - limit: Number of records to return (default: 100)
    - offset: Number of records to skip (default: 0)
    - account_number: Filter by account number
    - share_name: Filter by share name
    - type: Filter by type (Buy, Sell, Dividend, etc.)
    """
    queryset = InvestecJseTransaction.objects.all()
    
    # Apply filters
    account_number = request.query_params.get('account_number', None)
    if account_number:
        queryset = queryset.filter(account_number=account_number)
    
    share_name = request.query_params.get('share_name', None)
    if share_name:
        queryset = queryset.filter(share_name__icontains=share_name)
    
    transaction_type = request.query_params.get('type', None)
    if transaction_type:
        queryset = queryset.filter(type__icontains=transaction_type)
    
    # Apply pagination
    limit = int(request.query_params.get('limit', 100))
    offset = int(request.query_params.get('offset', 0))
    
    total_count = queryset.count()
    transactions = queryset[offset:offset + limit]
    
    serializer = InvestecJseTransactionSerializer(transactions, many=True)
    
    return Response({
        'count': total_count,
        'limit': limit,
        'offset': offset,
        'results': serializer.data
    })

# ------------------------------------------------
# Import Portfolio Data
# ------------------------------------------------

def process_portfolio_file(uploaded_file):
    """
    Helper function to process a single portfolio Excel file.
    Returns a dict with results or error information.
    """
    # Validate file extension
    if not uploaded_file.name.endswith(('.xlsx', '.xls')):
        return {
            'success': False,
            'filename': uploaded_file.name,
            'error': 'Invalid file format. Please upload an Excel file (.xlsx or .xls).'
        }
    
    try:
        # Read Excel file without header to inspect structure
        df_raw = pd.read_excel(uploaded_file, header=None)
        
        # First, find the row containing "Portfolio Holdings Report"
        report_row = None
        for idx, row in df_raw.iterrows():
            row_str = ' '.join([str(val) for val in row.values if pd.notna(val)])
            if 'portfolio holdings report' in row_str.lower():
                report_row = idx
                break
        
        if report_row is None:
            return {
                'success': False,
                'filename': uploaded_file.name,
                'error': 'Could not find "Portfolio Holdings Report" header in Excel file.'
            }
        
        # Extract date from Excel file - look for date patterns in rows around the report header
        portfolio_date = None
        
        # Try to extract date from filename first (format: Holdings-YYYYMMDD...)
        filename = uploaded_file.name
        date_match = re.search(r'(\d{8})', filename)
        if date_match:
            try:
                date_str = date_match.group(1)
                portfolio_date = pd.to_datetime(date_str, format='%Y%m%d').date()
            except:
                pass
        
        # If not found in filename, look for date in Excel rows around the report header
        if portfolio_date is None:
            # Check rows before and after the report header for date patterns
            search_rows = list(range(max(0, report_row - 5), min(len(df_raw), report_row + 5)))
            for idx in search_rows:
                row = df_raw.iloc[idx]
                for cell_val in row.values:
                    if pd.notna(cell_val):
                        cell_str = str(cell_val).strip()
                        # Try various date formats
                        for date_format in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y%m%d', '%d %B %Y', '%d %b %Y']:
                            try:
                                portfolio_date = pd.to_datetime(cell_str, format=date_format).date()
                                break
                            except:
                                try:
                                    # Try pandas flexible parsing
                                    portfolio_date = pd.to_datetime(cell_str).date()
                                    break
                                except:
                                    continue
                    if portfolio_date:
                        break
                if portfolio_date:
                    break
        
        if portfolio_date is None:
            return {
                'success': False,
                'filename': uploaded_file.name,
                'error': 'Could not extract date from Excel file. Please ensure the file contains a date near the "Portfolio Holdings Report" header or in the filename (format: YYYYMMDD).'
            }
        
        # Find header row starting from the row after "Portfolio Holdings Report"
        header_row = None
        for idx in range(report_row + 1, len(df_raw)):
            row = df_raw.iloc[idx]
            row_str = ' '.join([str(val).lower() for val in row.values if pd.notna(val)])
            if 'instrument description' in row_str and 'total quantity' in row_str:
                header_row = idx
                break
        
        if header_row is None:
            return {
                'success': False,
                'filename': uploaded_file.name,
                'error': 'Could not find header row (with "Instrument Description" and "Total Quantity") after "Portfolio Holdings Report".'
            }
        
        # Read with header row
        df = pd.read_excel(uploaded_file, header=header_row)
        
        # Map columns by name (from Excel structure)
        instrument_col = 'Instrument Description'
        quantity_col = 'Total Quantity'
        currency_col = 'Currency'
        unit_cost_col = 'Unit'  # Unit Cost (net)
        total_cost_col = 'Total Cost'
        price_col = 'Price'
        total_value_col = 'Total Value'
        exchange_rate_col = 'Exchange'  # Exchange Rate
        move_percent_col = 'Move (%)'
        portfolio_percent_col = 'Portfolio'  # Portfolio (%)
        profit_loss_col = 'Profit/Loss'
        annual_income_col = 'Annual'  # Annual Income (R)
        
        # Check if columns exist
        col_names = list(df.columns)
        missing_cols = []
        for col_name, col_var in [
            (instrument_col, 'Instrument Description'),
            (quantity_col, 'Total Quantity'),
            (currency_col, 'Currency'),
            (unit_cost_col, 'Unit'),
            (total_cost_col, 'Total Cost'),
            (price_col, 'Price'),
            (total_value_col, 'Total Value'),
        ]:
            if col_name not in col_names:
                missing_cols.append(col_var)
        
        if missing_cols:
            return {
                'success': False,
                'filename': uploaded_file.name,
                'error': f'Missing required columns: {", ".join(missing_cols)}',
                'available_columns': col_names[:30]
            }
        
        # Clear existing portfolio data for this month/year (not just the specific date)
        deleted_count = InvestecJsePortfolio.objects.filter(
            year=portfolio_date.year,
            month=portfolio_date.month
        ).delete()[0]
        
        # Prepare data for bulk creation
        portfolios_to_create = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Get instrument description
                instrument_desc = row[instrument_col]
                if pd.isna(instrument_desc) or str(instrument_desc).strip() == '':
                    continue
                
                # Extract company and share_code from "ABSA GROUP LIMITED (ABG)"
                instrument_str = str(instrument_desc).strip()
                company = ''
                share_code = ''
                
                # Pattern: "COMPANY NAME (CODE)"
                match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', instrument_str)
                if match:
                    company = match.group(1).strip()
                    share_code = match.group(2).strip()
                else:
                    # If no parentheses, use full string as company
                    company = instrument_str
                    share_code = ''
                
                # Get quantity - only process rows with quantity
                quantity_value = row[quantity_col]
                if pd.isna(quantity_value):
                    continue  # Skip rows without quantity (totals/headers)
                
                # Convert quantity - handle string values like " 910.00" or "1 959.00"
                if isinstance(quantity_value, str):
                    quantity_value = quantity_value.replace(' ', '').replace(',', '').strip()
                
                try:
                    quantity = Decimal(str(quantity_value))
                    if quantity == 0:
                        continue  # Skip rows with zero quantity
                except (InvalidOperation, ValueError):
                    continue  # Skip invalid quantity rows (totals/headers)
                
                # Get other required fields
                currency = str(row[currency_col])[:10] if not pd.isna(row[currency_col]) else 'ZAR'
                
                # Unit cost
                unit_cost_value = row[unit_cost_col]
                if pd.isna(unit_cost_value):
                    errors.append(f'Row {index + header_row + 2}: Unit cost is missing')
                    continue
                try:
                    unit_cost = Decimal(str(unit_cost_value))
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {index + header_row + 2}: Invalid unit cost: {unit_cost_value}')
                    continue
                
                # Total cost
                total_cost_value = row[total_cost_col]
                if pd.isna(total_cost_value):
                    errors.append(f'Row {index + header_row + 2}: Total cost is missing')
                    continue
                try:
                    total_cost = Decimal(str(total_cost_value))
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {index + header_row + 2}: Invalid total cost: {total_cost_value}')
                    continue
                
                # Price
                price_value = row[price_col]
                if pd.isna(price_value):
                    errors.append(f'Row {index + header_row + 2}: Price is missing')
                    continue
                try:
                    price = Decimal(str(price_value))
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {index + header_row + 2}: Invalid price: {price_value}')
                    continue
                
                # Total value
                total_value_value = row[total_value_col]
                if pd.isna(total_value_value):
                    errors.append(f'Row {index + header_row + 2}: Total value is missing')
                    continue
                try:
                    total_value = Decimal(str(total_value_value))
                except (InvalidOperation, ValueError):
                    errors.append(f'Row {index + header_row + 2}: Invalid total value: {total_value_value}')
                    continue
                
                # Optional fields
                exchange_rate = None
                if exchange_rate_col in col_names and not pd.isna(row[exchange_rate_col]):
                    try:
                        exchange_rate = Decimal(str(row[exchange_rate_col]))
                    except (InvalidOperation, ValueError):
                        pass
                
                move_percent = None
                if move_percent_col in col_names and not pd.isna(row[move_percent_col]):
                    try:
                        move_percent = Decimal(str(row[move_percent_col]))
                    except (InvalidOperation, ValueError):
                        pass
                
                portfolio_percent = None
                if portfolio_percent_col in col_names and not pd.isna(row[portfolio_percent_col]):
                    try:
                        portfolio_percent = Decimal(str(row[portfolio_percent_col]))
                    except (InvalidOperation, ValueError):
                        pass
                
                profit_loss = None
                if profit_loss_col in col_names and not pd.isna(row[profit_loss_col]):
                    try:
                        profit_loss = Decimal(str(row[profit_loss_col]))
                    except (InvalidOperation, ValueError):
                        pass
                
                # Annual Income (R)
                annual_income_zar = None
                if annual_income_col in col_names and not pd.isna(row[annual_income_col]):
                    try:
                        annual_income_zar = Decimal(str(row[annual_income_col]))
                    except (InvalidOperation, ValueError):
                        pass
                
                portfolios_to_create.append(
                    InvestecJsePortfolio(
                        date=portfolio_date,
                        year=portfolio_date.year,
                        month=portfolio_date.month,
                        day=portfolio_date.day,
                        company=company[:100],
                        share_code=share_code[:20],
                        quantity=quantity,
                        currency=currency,
                        unit_cost=unit_cost,
                        total_cost=total_cost,
                        price=price,
                        total_value=total_value,
                        exchange_rate=exchange_rate,
                        move_percent=move_percent,
                        portfolio_percent=portfolio_percent,
                        profit_loss=profit_loss,
                        annual_income_zar=annual_income_zar,
                    )
                )
            except Exception as e:
                errors.append(f'Row {index + header_row + 2}: {str(e)}')
                continue
        
        # Bulk create portfolios
        created_count = 0
        if portfolios_to_create:
            with transaction.atomic():
                created_instances = InvestecJsePortfolio.objects.bulk_create(
                    portfolios_to_create,
                    ignore_conflicts=False
                )
                created_count = len(created_instances)
        
        # Retrieve and serialize the created data
        portfolio_data = []
        if created_count > 0:
            # Query the created portfolios by date and company/share_code to get full data with IDs
            portfolios = InvestecJsePortfolio.objects.filter(date=portfolio_date).order_by('company', 'share_code')
            portfolio_data = InvestecJsePortfolioSerializer(portfolios, many=True).data
        
        # Prepare response
        return {
            'success': True,
            'filename': uploaded_file.name,
            'message': f'Successfully imported {created_count} portfolio holdings',
            'date': str(portfolio_date),
            'year': portfolio_date.year,
            'month': portfolio_date.month,
            'deleted_previous': deleted_count,
            'total_rows': len(df),
            'created': created_count,
            'errors': len(errors),
            'data': portfolio_data,
            'error_details': errors[:50] if errors else []  # Limit to first 50 errors
        }
        
    except pd.errors.EmptyDataError:
        return {
            'success': False,
            'filename': uploaded_file.name,
            'error': 'The Excel file is empty.'
        }
    except Exception as e:
        return {
            'success': False,
            'filename': uploaded_file.name,
            'error': f'Error processing file: {str(e)}'
        }


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def portfolio_upload_view(request):
    """
    API endpoint to upload Excel file(s) and import portfolio holdings.
    
    Accepts POST request with 'file' or 'files' field(s) containing Excel file(s).
    Date is extracted from each Excel file itself.
    
    For each file, all portfolio data for that month/year will be deleted before importing.
    This ensures only one version per month is kept.
    
    Returns import statistics, imported data, and any errors encountered for each file.
    """
    # Get files - support both 'file' (single) and 'files' (multiple)
    uploaded_files = []
    if 'files' in request.FILES:
        uploaded_files = request.FILES.getlist('files')
    elif 'file' in request.FILES:
        uploaded_files = [request.FILES['file']]
    else:
        return Response(
            {'error': 'No file provided. Please upload an Excel file (use "file" or "files" field).'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if not uploaded_files:
        return Response(
            {'error': 'No file provided. Please upload an Excel file.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Process each file
    results = []
    total_created = 0
    total_deleted = 0
    total_errors = 0
    
    for uploaded_file in uploaded_files:
        result = process_portfolio_file(uploaded_file)
        results.append(result)
        
        if result.get('success'):
            total_created += result.get('created', 0)
            total_deleted += result.get('deleted_previous', 0)
            total_errors += result.get('errors', 0)
    
    # Prepare aggregated response
    successful_files = [r for r in results if r.get('success')]
    failed_files = [r for r in results if not r.get('success')]
    
    response_data = {
        'success': len(failed_files) == 0,
        'total_files': len(uploaded_files),
        'successful_files': len(successful_files),
        'failed_files': len(failed_files),
        'total_created': total_created,
        'total_deleted': total_deleted,
        'total_errors': total_errors,
        'files': results,
    }
    
    status_code = status.HTTP_201_CREATED if total_created > 0 else status.HTTP_200_OK
    if failed_files:
        status_code = status.HTTP_207_MULTI_STATUS  # Multi-Status if some files failed
    
    return Response(response_data, status=status_code)


# ------------------------------------------------
# Share Name Mapping
# ------------------------------------------------

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def mapping_upload_view(request):
    """
    API endpoint to upload Excel file and import share name mappings.
    
    Accepts POST request with 'file' field containing Excel file.
    Expected columns: Share_Name, Company, Share_Code
    Company and Share_Code are optional.
    
    Returns import statistics and any errors encountered.
    """
    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided. Please upload an Excel file.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    uploaded_file = request.FILES['file']
    
    # Validate file extension
    if not uploaded_file.name.endswith(('.xlsx', '.xls')):
        return Response(
            {'error': 'Invalid file format. Please upload an Excel file (.xlsx or .xls).'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Read Excel file
        df = pd.read_excel(uploaded_file)
        
        # Normalize column names
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('-', '_')
        
        # Map column names
        share_name_col = None
        company_col = None
        share_code_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            if 'share_name' in col_lower or 'sharename' in col_lower:
                share_name_col = col
            elif 'company' in col_lower:
                company_col = col
            elif 'share_code' in col_lower or 'sharecode' in col_lower or 'code' in col_lower:
                share_code_col = col
        
        if not share_name_col:
            return Response(
                {
                    'error': 'Missing required column: Share_Name',
                    'available_columns': list(df.columns)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Prepare data for bulk create/update
        mappings_to_create = []
        mappings_to_update = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                share_name = str(row[share_name_col]).strip() if not pd.isna(row[share_name_col]) else ''
                if not share_name:
                    continue
                
                company = str(row[company_col]).strip()[:100] if company_col and not pd.isna(row[company_col]) else ''
                share_code = str(row[share_code_col]).strip()[:20] if share_code_col and not pd.isna(row[share_code_col]) else ''
                
                # Check if mapping exists
                try:
                    existing = InvestecJseShareNameMapping.objects.get(share_name=share_name)
                    # Update existing
                    if company:
                        existing.company = company
                    if share_code:
                        existing.share_code = share_code
                    mappings_to_update.append(existing)
                except InvestecJseShareNameMapping.DoesNotExist:
                    # Create new
                    mappings_to_create.append(
                        InvestecJseShareNameMapping(
                            share_name=share_name,
                            company=company if company else None,
                            share_code=share_code if share_code else None,
                        )
                    )
            except Exception as e:
                errors.append(f'Row {index + 2}: {str(e)}')
                continue
        
        # Bulk create and update
        created_count = 0
        updated_count = 0
        
        if mappings_to_create:
            with transaction.atomic():
                created_instances = InvestecJseShareNameMapping.objects.bulk_create(
                    mappings_to_create,
                    ignore_conflicts=False
                )
                created_count = len(created_instances)
        
        if mappings_to_update:
            with transaction.atomic():
                InvestecJseShareNameMapping.objects.bulk_update(
                    mappings_to_update,
                    ['company', 'share_code']
                )
                updated_count = len(mappings_to_update)
        
        response_data = {
            'success': True,
            'message': f'Successfully imported {created_count} new mappings and updated {updated_count} existing mappings',
            'created': created_count,
            'updated': updated_count,
            'errors': len(errors),
        }
        
        if errors:
            response_data['error_details'] = errors[:50]
            if len(errors) > 50:
                response_data['error_details'].append(f'... and {len(errors) - 50} more errors')
        
        return Response(response_data, status=status.HTTP_201_CREATED if created_count > 0 or updated_count > 0 else status.HTTP_200_OK)
        
    except pd.errors.EmptyDataError:
        return Response(
            {'error': 'The Excel file is empty.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': f'Error processing file: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def export_companies_view(request):
    """
    API endpoint to export all unique companies from portfolios.
    
    Returns a list of companies with their share codes.
    """
    companies = InvestecJsePortfolio.objects.values('company', 'share_code').distinct().order_by('company')
    
    # Format as list
    companies_list = [
        {
            'company': item['company'],
            'share_code': item['share_code']
        }
        for item in companies
    ]
    
    return Response({
        'count': len(companies_list),
        'companies': companies_list
    })


@api_view(['GET'])
def export_share_names_view(request):
    """
    API endpoint to export all unique share names from transactions.
    
    Returns a list of share names.
    """
    share_names = InvestecJseTransaction.objects.exclude(
        share_name=''
    ).exclude(
        share_name__isnull=True
    ).values_list('share_name', flat=True).distinct().order_by('share_name')
    
    share_names_list = list(share_names)
    
    return Response({
        'count': len(share_names_list),
        'share_names': share_names_list
    })


@api_view(['GET'])
def export_transactions_view(request):
    """
    API endpoint to export all InvestecJseTransaction data to Excel file.
    
    Exports all transactions to an Excel file in the source files directory.
    """
    try:
        # Get all transactions
        transactions = InvestecJseTransaction.objects.all().order_by('-date', '-created_at')
        
        # Convert to list of dictionaries
        transactions_data = []
        for txn in transactions:
            # Convert timezone-aware datetimes to timezone-naive for Excel compatibility
            created_at = txn.created_at.replace(tzinfo=None) if txn.created_at else None
            updated_at = txn.updated_at.replace(tzinfo=None) if txn.updated_at else None
            
            transactions_data.append({
                'Date': txn.date,
                'Year': txn.year,
                'Month': txn.month,
                'Day': txn.day,
                'Account Number': txn.account_number,
                'Description': txn.description,
                'Share Name': txn.share_name,
                'Type': txn.type,
                'Quantity': float(txn.quantity) if txn.quantity else None,
                'Value': float(txn.value) if txn.value else None,
                'Value Per Share': float(txn.value_per_share) if txn.value_per_share else None,
                'Value Calculated': float(txn.value_calculated) if txn.value_calculated else None,
                'Created At': created_at,
                'Updated At': updated_at,
            })
        
        # Create DataFrame
        df = pd.DataFrame(transactions_data)
        
        # Get the source files directory path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        source_files_dir = os.path.join(current_dir, 'source files')
        
        # Ensure directory exists
        os.makedirs(source_files_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'InvestecJseTransaction_Export_{timestamp}.xlsx'
        filepath = os.path.join(source_files_dir, filename)
        
        # Export to Excel
        df.to_excel(filepath, index=False, engine='openpyxl')
        
        return Response({
            'success': True,
            'message': f'Successfully exported {len(transactions_data)} transactions to Excel',
            'filename': filename,
            'filepath': filepath,
            'count': len(transactions_data)
        })
        
    except Exception as e:
        return Response(
            {'error': f'Error exporting transactions: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
